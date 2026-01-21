from abc import ABC, abstractmethod

class MotorController(ABC):
    @abstractmethod
    def process_command(self, command: dict):
        """
        Process a control command.
        command: dict containing 'w', 'a' values or similar.
        """
        pass
