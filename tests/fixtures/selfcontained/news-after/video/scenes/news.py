"""Fixture for tests/test_selfcontained.py: a news video that says the same on its own terms."""
from common import RAScene


class Hook(RAScene):
    def construct(self):
        with self.voiceover(text="A million robots, and not one collision. [pause 1] How?"):
            pass
        with self.voiceover(text="A planner that solves only for the touches handled a million robots."):
            pass


class Limits(RAScene):
    def construct(self):
        with self.voiceover(text="So far that's only idealized robots in simulation, so the numbers may still change."):
            pass
