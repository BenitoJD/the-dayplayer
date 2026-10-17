# Trust Manifest — what The Dayplayer records and never records

The Dayplayer can only work if people believe it can't spy on them.
This file is the promise, and the code is the proof — the recorder is
open for anyone to read.

## NEVER recorded

- **Which keys you press.** A letter is logged as `"key"` — every letter,
  every digit, every punctuation mark, the same class. There is no table
  anywhere mapping keys to characters.
- Words, sentences, passwords (same rule: a password is just `key…key`).
- Window titles, tab titles, file names, URLs.
- Screen content, clipboard, microphone, camera, network traffic.
- Anything uploaded anywhere. There is no server, no account, no telemetry.
  The code contains zero network calls in the recorder and composer.

## What IS recorded (per event: a timestamp + a few bytes)

- Key **down/up** and a coarse class: `key`, `space`, `enter`, `tab`,
  `backspace`, `mod` (shift/cmd/ctrl/alt), `arrow`, `fn`, `other`.
  Classes exist because structure (tab-flailing, shift-holding) is the
  signal — they carry no content.
- Mouse: approximate distances (throttled), click down/up, scroll direction.
- Foreground **app name** only (e.g. "Safari"), on change.
- A heartbeat every minute (proves the daemon is alive).

## Where data lives

`~/.dayplayer/` — plain JSONL files on your disk. Not in any repo, not in
any cloud. Delete the folder and everything is gone. Sharing is explicit:
you render a piece of audio and you choose to share that audio. Renders
contain no raw events.

## Honest caveat (we say this out loud)

Timing behavior alone can still act as a behavioral fingerprint —
keystroke-rhythm research shows people can be re-identified from their
typing patterns. That's why raw logs must stay local by design, and why
"share" means sharing a rendered piece of music, never your logs.

## For the future

If a cloud version ever exists (e.g. storing renders), raw event logs
still never leave the device. If that promise ever changes, this project
has betrayed its users — fork the last honest version.
