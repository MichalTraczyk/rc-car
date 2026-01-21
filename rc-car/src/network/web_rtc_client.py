import asyncio
import json
import logging
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCIceCandidate, RTCConfiguration, RTCIceServer
import socketio

logger = logging.getLogger(__name__)

class RCCarWebRTCClient:
    def __init__(self, room_code, signaling_url, motor_controller, video_track_factory):
        self.room_code = room_code
        self.signaling_url = signaling_url
        self.motor_controller = motor_controller
        self.video_track_factory = video_track_factory
        
        self.sio = socketio.AsyncClient()
        self.pc = None
        self.video_track = None
        self.datachannel = None

        self._setup_socketio_events()

    def _setup_socketio_events(self):
        @self.sio.event
        async def connect():
            logger.info(f"Connected to signaling server")
            await self.sio.emit('register-car', self.room_code)
            logger.info(f"Car registered with room code: {self.room_code}")

        @self.sio.event
        async def disconnect():
            logger.info("Disconnected from signaling server")

        @self.sio.on('controller-joined')
        async def on_controller_joined(data):
            logger.info("Controller joined the room")
            await self.create_offer()

        @self.sio.on('answer')
        async def on_answer(data):
            await self.handle_answer(data)

        @self.sio.on('ice-candidate')
        async def on_ice_candidate(data):
            await self.handle_ice_candidate(data)

    async def connect_signaling(self):
        """Connect to signaling server"""
        try:
            await self.sio.connect(self.signaling_url)
            logger.info("Waiting for controller to join...")
        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            raise

    async def initialize_peer_connection(self):
        """Initialize WebRTC peer connection"""
        config = RTCConfiguration(
            iceServers=[
                RTCIceServer(urls=["stun:stun.l.google.com:19302"]),
                RTCIceServer(urls=["stun:stun1.l.google.com:19302"])
            ]
        )

        self.pc = RTCPeerConnection(configuration=config)
        self.datachannel = self.pc.createDataChannel("control")
        logger.info("Data channel control created")

        @self.datachannel.on("message")
        def on_message(message):
            try:
                data = json.loads(message)
                # Delegate to motor controller
                self.motor_controller.process_command(data)
            except Exception as e:
                logger.error(f"Failed to parse control data: {e}")

        @self.datachannel.on("open")
        def on_open():
            logger.info("Data Channel is OPEN and ready for commands")

        @self.pc.on("icecandidate")
        async def on_icecandidate(candidate):
            if candidate:
                await self.send_ice_candidate(candidate)

        @self.pc.on("iceconnectionstatechange")
        async def on_iceconnectionstatechange():
            logger.info(f"ICE connection state: {self.pc.iceConnectionState}")

        @self.pc.on("connectionstatechange")
        async def on_connectionstatechange():
            logger.info(f"Connection state: {self.pc.connectionState}")

        # Add video track from factory
        self.video_track = self.video_track_factory()
        self.pc.addTrack(self.video_track)
        logger.info("Video track added")

    async def create_offer(self):
        """Create and send WebRTC offer"""
        try:
            if self.pc is None:
                await self.initialize_peer_connection()

            offer = await self.pc.createOffer()
            await self.pc.setLocalDescription(offer)

            logger.info("Offer created")

            offer_data = {
                "type": self.pc.localDescription.type,
                "sdp": self.pc.localDescription.sdp
            }

            await self.sio.emit('offer', {
                'roomCode': self.room_code,
                'offer': json.dumps(offer_data)
            })

            logger.info("Offer sent")

        except Exception as e:
            logger.error(f"Failed to create offer: {e}")

    async def handle_answer(self, data):
        """Handle answer from controller"""
        try:
            answer_json = data.get('answer')
            answer_data = json.loads(answer_json)

            logger.info("Received answer")

            answer = RTCSessionDescription(
                sdp=answer_data['sdp'],
                type=answer_data['type']
            )

            await self.pc.setRemoteDescription(answer)
            logger.info("Remote description set successfully")

        except Exception as e:
            logger.error(f"Failed to handle answer: {e}")

    async def handle_ice_candidate(self, data):
        """Handle ICE candidate from controller"""
        try:
            candidate_json = data.get('candidate')
            candidate_data = json.loads(candidate_json)

            logger.info("Received ICE candidate")

            candidate = RTCIceCandidate(
                candidate=candidate_data['candidate'],
                sdpMid=candidate_data['sdpMid'],
                sdpMLineIndex=candidate_data['sdpMLineIndex']
            )

            await self.pc.addIceCandidate(candidate)

        except Exception as e:
            logger.error(f"Failed to handle ICE candidate: {e}")

    async def send_ice_candidate(self, candidate):
        """Send ICE candidate to controller"""
        try:
            if candidate.candidate:
                candidate_data = {
                    "candidate": candidate.candidate,
                    "sdpMid": candidate.sdpMid,
                    "sdpMLineIndex": candidate.sdpMLineIndex
                }

                await self.sio.emit('ice-candidate', {
                    'roomCode': self.room_code,
                    'candidate': json.dumps(candidate_data)
                })

        except Exception as e:
            logger.error(f"Failed to send ICE candidate: {e}")

    async def run(self):
        """Main run loop"""
        try:
            await self.connect_signaling()

            logger.info(f"RC Car Simulator running with room code: {self.room_code}")
            logger.info("Connect from Unity by selecting this car")
            logger.info("Press Ctrl+C to stop")

            # Keep running
            while True:
                await asyncio.sleep(1)

        except KeyboardInterrupt:
            logger.info("Shutting down...")
        except Exception as e:
            logger.error(f"Error: {e}")
        finally:
            await self.cleanup()

    async def cleanup(self):
        """Clean up resources"""
        logger.info("Cleaning up...")

        if self.pc:
            await self.pc.close()

        if self.sio.connected:
            await self.sio.disconnect()

        logger.info("Cleanup complete")
