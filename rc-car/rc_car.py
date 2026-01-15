import asyncio
import json
import logging
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCIceCandidate, VideoStreamTrack, RTCConfiguration, \
    RTCIceServer
import socketio
import numpy as np
import cv2
import av
from fractions import Fraction

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TestPatternVideoTrack(VideoStreamTrack):
    """
    Generates a test pattern video stream (moving color bars)
    Perfect for testing without a real camera
    """

    def __init__(self, width=640, height=480, fps=30):
        super().__init__()
        self.width = width
        self.height = height
        self.fps = fps
        self.counter = 0
        logger.info(f"Test pattern video track initialized: {width}x{height} @ {fps}fps")

    async def recv(self):
        """
        Generate and return a test pattern video frame
        """
        pts, time_base = await self.next_timestamp()

        # Create a test pattern (moving color bars)
        frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)

        # Create moving vertical color bars
        bar_width = self.width // 7
        colors = [
            [255, 255, 255],  # White
            [255, 255, 0],  # Yellow
            [0, 255, 255],  # Cyan
            [0, 255, 0],  # Green
            [255, 0, 255],  # Magenta
            [255, 0, 0],  # Red
            [0, 0, 255],  # Blue
        ]

        offset = (self.counter % self.width)
        for i, color in enumerate(colors):
            x_start = (i * bar_width + offset) % self.width
            x_end = min(x_start + bar_width, self.width)
            frame[:, x_start:x_end] = color

            # Handle wraparound
            if x_start + bar_width > self.width:
                overflow = (x_start + bar_width) - self.width
                frame[:, 0:overflow] = color

        # Add frame counter text using OpenCV
        text = f"Frame: {self.counter}"
        cv2.putText(frame, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)

        self.counter += 1

        # Convert to aiortc VideoFrame
        video_frame = av.VideoFrame.from_ndarray(frame, format="bgr24")
        video_frame.pts = pts
        video_frame.time_base = time_base

        return video_frame


class RCCarSimulator:
    def __init__(self, room_code, signaling_url="http://localhost:8080"):
        self.room_code = room_code
        self.signaling_url = signaling_url
        self.sio = socketio.AsyncClient()
        self.pc = None
        self.video_track = None
        self.datachannel = None

        # Setup Socket.IO event handlers
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
                logger.info(f"CONTROL INPUT: W/S: {data.get('w'):.2f} | A/D: {data.get('a'):.2f}")
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

        # Add test pattern video track
        self.video_track = TestPatternVideoTrack(width=640, height=480, fps=30)
        self.pc.addTrack(self.video_track)
        logger.info("Test pattern video track added")

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


async def main():
    """Main entry point"""
    import sys

    # Get room code from command line or use default
    room_code = sys.argv[1] if len(sys.argv) > 1 else "CAR001"
    signaling_url = sys.argv[2] if len(sys.argv) > 2 else "https://rc-signaling-serv-816336414350.europe-west1.run.app"

    logger.info("=" * 60)
    logger.info("RC Car Simulator - Docker Test Environment")
    logger.info("=" * 60)
    logger.info(f"Room Code: {room_code}")
    logger.info(f"Signaling Server: {signaling_url}")
    logger.info("=" * 60)

    car = RCCarSimulator(room_code, signaling_url)
    await car.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped by user")