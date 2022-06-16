from ..kobold import world


class DummyMessage:
    def __init__(self, channel, author, content, w=None, k=None):
        self.channel = channel
        self.author = author
        self.content = content
        if not w:
            self.world = world
        else:
            self.world = w
        self.k = k

    def delete(self):
        pass
