class CerebusCommInterface:
    def start(self):
        # TODO: This needs to be after threading.Thread in MRO so CerebusComm must be the second in the mix-in.
        raise NotImplementedError

    def stop(self):
        raise NotImplementedError

    def send(self, send_bytes):
        raise NotImplementedError
