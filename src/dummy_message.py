class DummyMessage:
    def __init__(self, channel, author, content, w, k=None):
        self.channel = channel
        self.author = author
        self.content = content
        self.world = w
        self.k = k
