"""Fixture for tests/test_selfcontained.py: a news video that names the publication it covers and its authors."""
from common import RAScene


class Hook(RAScene):
    def construct(self):
        with self.voiceover(text="A million robots, and not one collision. [pause 1] How?"):
            pass
        with self.voiceover(text="That's how the authors planned a million robots."):
            pass


class Limits(RAScene):
    def construct(self):
        with self.voiceover(text="The paper is a preprint, so the numbers may still change."):
            pass
