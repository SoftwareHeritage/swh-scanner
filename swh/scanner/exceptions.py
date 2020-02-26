class InvalidPath(Exception):
    def __str__(self):
        return 'the provided path is invalid: "%s"' % self.args


class APIError(Exception):
    def __str__(self):
        return 'API Error: "%s"' % self.args
