"""Tiny text protocol spoken over UDP to the alarm clock.

PC -> device (UDP, port 5006):
    LISTEN            stop the radio and start the mic
    PLAY <http-url>   stop the mic and play a WAV/MP3 as an announcement
    STOP              stop the mic
    PING              liveness probe (device logs it)

No framing, no JSON: one command per datagram, UTF-8, trailing newline optional.

Device -> PC (UDP, port 5005, the audio uplink):
    WAKE              4-byte signal sent when the on-device wake word fires
    <PCM>             512-byte 16-bit mono frames at 16 kHz

WAKE rides the audio port because the command port's send path never reached
the PC (see README "Blockers"); PCM and WAKE are told apart by length.
"""

from __future__ import annotations

from dataclasses import dataclass

PLAY = "PLAY"
STOP = "STOP"
PING = "PING"
LISTEN = "LISTEN"


@dataclass(frozen=True)
class Command:
    verb: str
    arg: str = ""

    def encode(self) -> bytes:
        return (f"{self.verb} {self.arg}".strip() + "\n").encode("utf-8")


def play(url: str) -> Command:
    if not url:
        raise ValueError("play() needs a URL")
    return Command(PLAY, url)


def stop() -> Command:
    return Command(STOP)


def ping() -> Command:
    return Command(PING)


def listen() -> Command:
    return Command(LISTEN)


def decode(payload: bytes) -> Command:
    text = payload.decode("utf-8", errors="replace").strip()
    verb, _, arg = text.partition(" ")
    return Command(verb.upper(), arg.strip())
