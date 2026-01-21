import asyncio
import logging
import sys
import os

from src.network.web_rtc_client import RCCarWebRTCClient
from src.control.dummy_motor import DummyMotorController
from src.video.test_pattern import TestPatternVideoTrack

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_video_track():
    """Factory function for video track"""
    return TestPatternVideoTrack(width=640, height=480, fps=30)

async def main():
    """Main entry point"""
    import sys

    # Get room code from command line or use default
    room_code = sys.argv[1] if len(sys.argv) > 1 else "CAR001"
    signaling_url = sys.argv[2] if len(sys.argv) > 2 else "https://rc-signaling-serv-816336414350.europe-west1.run.app"

    logger.info("=" * 60)
    logger.info("RC Car Simulator - Refactored Structure")
    logger.info("=" * 60)
    logger.info(f"Room Code: {room_code}")
    logger.info(f"Signaling Server: {signaling_url}")
    logger.info("=" * 60)

    # Initialize components
    motor_controller = DummyMotorController()
    
    # Create client with dependencies
    car = RCCarWebRTCClient(
        room_code=room_code,
        signaling_url=signaling_url,
        motor_controller=motor_controller,
        video_track_factory=create_video_track
    )
    
    await car.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped by user")
