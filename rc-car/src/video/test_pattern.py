import logging
import numpy as np
import cv2
import av
from aiortc import VideoStreamTrack

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
