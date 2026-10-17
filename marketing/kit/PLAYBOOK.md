# Circadia: the X playbook

Everything below is ready to post. Copy, paste, attach the named asset.

Assets live next to this file:
`hero-card.png` · `trust-card.png` · `patterns-card.png` · `day-shapes.png` ·
`blind-card.png` · `circadia-ad.mp4` (45s hero) · `blind-test.mp4` (32s) ·
`live-clip.mp4` (18s)

---

## 0. Before the first post

**Handle ideas:** `@circadia_app`, `@yourdayplayed`, `@circadia_hq`

**Bio:**
> Your workday, played back. Circadia listens to the timing of your input,
> never the content, and turns the day into music. macOS + Windows. Free.

**Pinned post:** the hero (post 1 below) with `circadia-ad.mp4`.

**The link:** always `https://github.com/BenitoJD/the-dayplayer/releases/latest`

**Rule that decides your reach:** the link never goes in the main post. Put
it in the first reply, every time. X suppresses posts with outbound links.

---

## 1. Launch week calendar

| Day | Post | Asset |
|---|---|---|
| 1 | Hero: what it is | `circadia-ad.mp4` |
| 2 | The blind test | `blind-test.mp4` |
| 3 | What it never records | `trust-card.png` |
| 4 | Blind test answer + results | `blind-card.png` |
| 5 | Why I built it (ADHD angle) | `live-clip.mp4` |
| 6 | Four workdays, four shapes | `day-shapes.png` |
| 7 | The vocabulary | `patterns-card.png` |
| 8 | Build thread + week album | `hero-card.png` |

Post between 14:00 and 17:00 UTC (US morning, EU afternoon). One strong post
a day beats three weak ones. Reply to every comment for the first two hours.

---

## 2. The posts

### Post 1, hero (pin this)

> I recorded a week of keystrokes without recording a single letter.
>
> Only the timing. How long I paused. How fast I typed. How far my mouse went.
>
> Then I turned each day into music. This is a workday, played back.
>
> sound on.

**Reply 1:** `Free, macOS and Windows: https://github.com/BenitoJD/the-dayplayer/releases/latest`
**Reply 2:** `What it never touches: letters, words, passwords, window titles, URLs, clipboard, screen. Everything stays in a folder on your own machine. No server, no account.`

Alt text: `A dark circular ring filling with amber, red and blue segments while music plays, the words Flow and Flail appearing in the centre.`

---

### Post 2, the blind test

> Two versions of the same day.
>
> A is my real Tuesday. B is the exact same events with the timings shuffled.
>
> One of them sounds like me. Can you hear which? Reply A or B, I will post
> the answer tomorrow.

Attach `blind-test.mp4`. This is the post that earns replies, and replies are
what the algorithm rewards. Expect 5 to 20x the engagement of a normal post.

---

### Post 3, trust

> "Wait, you record keystrokes?"
>
> Never the keys. Every letter is logged as the same token. What is recorded
> is how long you paused, how far the mouse moved, and which app was in front.
>
> Nothing readable. Nothing uploaded. Open source, so you can check.

Attach `trust-card.png`.

---

### Post 4, the answer

> Yesterday I asked which clip was my real day. X of you said A, Y said B.
>
> It was B. Here is what gives it away: the real day has long steady runs
> where the same rhythm repeats. The shuffled one has all the same events,
> just no shape.

Attach `blind-card.png`. Always post the answer, even if the split was 50/50.
Honesty here builds the habit of people playing along next time.

---

### Post 5, the reason (strongest with the ADHD and time-blindness crowd)

> I cannot feel time passing. Meetings vanish, afternoons evaporate, and I
> only notice at 6pm.
>
> So I made my day audible. Fast typing is a drum. Alt-tabbing is a stutter.
> A long quiet stretch is one held chord.
>
> Now I can hear the shape of a day while I am inside it.

Attach `live-clip.mp4`.

---

### Post 6, four shapes

> Same person, same week. Four days.
>
> Deep work. Meetings. Firefighting. Scattered.
>
> I never believed my days had shapes until I could see them like this.

Attach `day-shapes.png`. Very quotable, expect people to repost with "which
one are you".

---

### Post 7, the vocabulary

> Four things a workday does, and what they sound like:
>
> Flow: steady typing, warm pulse, the work carrying you
> Flail: alt-tab storms, static creeping in
> Drift: mouse wandering, an airy wash
> Mire: meetings and reading, one low tone
>
> Once you have the words, you start noticing them live.

Attach `patterns-card.png`.

---

### Post 8, the build thread

> I built an app that turns your workday into music. Testing it properly
> found five bugs that would have shipped:
>
> 1. the recorder captured nothing, because macOS passes an extra argument
>    to every input callback
> 2. live mode was silent, because the audio callback signature was wrong
> 3. a 24 hour day rendered completely silent, 0 notes
> 4. browsing to an empty day crashed the window
> 5. recording inside a GUI app crashes the OS keyboard listener
>
> Thread on what "test it properly" actually means.

Then 4 to 6 replies, one bug each, ending with:

> The lesson: synthetic tests passed while the app was silently recording
> nothing. Only driving real events, a real window and a real audio device
> found it. github.com/BenitoJD/the-dayplayer

This one earns you the developer audience, which is the audience that
amplifies.

---

### The daily series (start it once the launch posts are done)

> Day 4 of turning my workdays into music.
>
> Today: 2h 41m of flow, one 38 minute run before lunch, and a 40 minute
> stretch that sounds like standing still.

Attach a fresh 20s render. Post it at the same time every day. This is what
turns a launch spike into an audience, because people follow a series.

---

## 3. Reply templates

**Link (always the first reply):**
> Free, no account, no installer drama: https://github.com/BenitoJD/the-dayplayer/releases/latest

**"Is this a keylogger?"**
> Fair question, and it is the first thing I would ask too. It logs the class
> of a keypress, never the key. Every letter is the same token. You can read
> the recorder, it is about 200 lines, and you can watch the file it writes.

**"Mac says unidentified developer":**
> Right-click the app, then Open, once. It is not notarized yet, which costs
> 99 dollars a year I have not spent. The warning is Gatekeeper, not a virus.

**"Windows says unknown publisher":**
> Same thing, unsigned build. More info, then Run anyway. Or build it
> yourself from source in one command.

**"Does it work on Windows?"**
> Yes, single .exe, lives in the tray, and Windows needs no permission
> prompts at all. The macOS build is the one that has to ask.

**"Why not mobile?"**
> Phones do not let an app see system-wide input timing, so a phone version
> would have to sonify something else. Desktop first.

**"This is a productivity app?"**
> Deliberately not. No scores, no streaks, no leaderboard. It is a mirror.
> The moment it grades you, it stops being yours.

---

## 4. Outreach, do this on day 1

Do not tag big accounts. Send this to 15 small ones (1k to 30k followers) in
ADHD and executive function, quantified self, indie hackers, music tech, and
privacy:

> Hi. I built something odd and I think your audience would get it: an app
> that turns the timing of your workday into music, never recording content.
> Here is a 30 second example. No ask, happy to send a free build if you want
> to try it on your own week.

Personalise the first line. Fifteen real messages beat one mass mention.

---

## 5. What not to do

- No link in the main post, ever
- Never lead with the tech stack or the word AI
- Never claim productivity gains. You built a mirror. Claiming optimization
  invites the surveillance comparison and loses the art crowd
- Never say "records keystrokes" without "timing only" in the same breath
- Do not post the same asset twice in a week
- Do not argue with the one person who calls it spyware. Answer once, warmly,
  then let the replies do the work

---

## 6. What to watch

| Metric | Why |
|---|---|
| Replies per post | The only engagement that drives reach |
| Release download counts | Real intent, visible on the GitHub release page |
| "Which one is you" answers | Whether the concept lands at all |
| Follows per post | Whether the series is worth continuing |

Ignore impressions. If people reply with their own A or B guesses, the idea
is working.
