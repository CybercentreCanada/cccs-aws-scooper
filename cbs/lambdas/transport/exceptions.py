class TransportError(Exception):
    def __init__(self, message: str, object_key: str = "", workload: str = "") -> None:
        super().__init__(message)
        self.object_key = object_key
        self.workload = workload
