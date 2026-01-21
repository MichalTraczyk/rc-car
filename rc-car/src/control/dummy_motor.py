import logging
from .motor_interface import MotorController

logger = logging.getLogger(__name__)

class DummyMotorController(MotorController):
    def process_command(self, command: dict):
        # Original logging logic
        w = command.get('w', 0.0)
        a = command.get('a', 0.0)
        logger.info(f"CONTROL INPUT: W/S: {w:.2f} | A/D: {a:.2f}")
