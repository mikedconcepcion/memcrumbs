"""Driver for the Fictional ProFire kiln controllers (serial COM ports or TCP)."""
import socket


class ControllerError(Exception):
    """Raised when a controller does not answer or reports a latched fault."""


class ControllerDriver:
    """Talk to one kiln controller using the register map from the vendor manual.

    Register 40001 is the process value in tenths of a degree C, 40002 the setpoint.
    A program loaded with ``load_program`` keeps running even if this host disconnects.
    """

    PV_REG = 40001
    SP_REG = 40002

    def __init__(self, kiln_id: str, link: str):
        self.kiln_id = kiln_id
        self.link = link  # 'COM3' or 'k3-ctl:502'
        self._sock = None

    def connect(self) -> None:
        """Open the TCP connection (serial links are opened by the platform layer)."""
        if ":" in self.link:
            host, port = self.link.rsplit(":", 1)
            self._sock = socket.create_connection((host, int(port)), timeout=5)

    def read_temp(self) -> float:
        """Return the current process value in degrees C."""
        return self._read_register(self.PV_REG) / 10.0

    def send_setpoint(self, temp_c: float) -> None:
        """Write a new setpoint; refuses values above the hard limit of 1285 C."""
        if temp_c > 1285:
            raise ControllerError(f"setpoint {temp_c} above hard limit")
        self._write_register(self.SP_REG, int(temp_c * 10))

    def load_program(self, segments: list[dict]) -> None:
        """Store a compiled profile in controller memory and start it."""
        for idx, seg in enumerate(segments):
            self._write_register(41000 + idx * 4, seg["target_c"] * 10)
            self._write_register(41001 + idx * 4, seg["rate_c_per_h"])
            self._write_register(41002 + idx * 4, seg["hold_min"])
        self._write_register(40010, 1)  # start

    def is_running(self) -> bool:
        """True when the controller reports a program in progress (used by --adopt)."""
        return self._read_register(40011) == 1

    def _read_register(self, reg: int) -> int:
        raise NotImplementedError("transport layer is platform specific")

    def _write_register(self, reg: int, value: int) -> None:
        raise NotImplementedError("transport layer is platform specific")
