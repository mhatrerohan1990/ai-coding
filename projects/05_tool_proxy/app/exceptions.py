class NotFoundError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class BadRequestError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message
