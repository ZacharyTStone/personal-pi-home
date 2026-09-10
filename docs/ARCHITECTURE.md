# Why it's built this way

This is a distillation of a hub that ran on a Raspberry Pi for a while
and accumulated a dozen jobs. Most of what's here isn't clever — it's the
handful of things that turned out to matter, written down so you don't
have to rediscover them.

If you only read one section, read the first two.

---

## Silence is a feature

The failure mode of a personal hub isn't crashing. It's becoming noise.

A job that pings you every fifteen minutes to say everything is fine
trains you, within about a week, to swipe its notifications away without
reading them. At that point it can't alert you either — you've built an
elaborate system for not being told things.

So: **most passes of most jobs should send nothing at all.** That's why
`run(ctx)` returns nothing and sending is an explicit call. Saying
nothing isn't an error path or a special case; it's the default, and the
code shape makes it the easiest thing to write.

The corollary, for alerting jobs: alert on the *crossing*, not the state.
Once you've been told the disk is at 91%, being told again at 91.2% is
noise. Record the level you last spoke at, and speak again only when it
gets materially worse — then once more when it recovers.

## The box will be off sometimes

Power cuts, reboots, a plug someone needed. Any schedule that assumes
continuous uptime is wrong.

Two properties, both in `schedule.py`, both tested:

- **Catch-up.** If the box was off at 07:00 and came back at 11:00, the
  07:00 message still goes out. A missed window is a late message, not a
  lost one.
- **Never twice.** Once a window has been served it stays served, however
  often the loop ticks.

The way you get both is to store the *last successful run* and compare it
against the window boundary — not to count down from the last run, and
not to ask "was anything sent in the last 24 hours". The difference shows
up the first time a catch-up message goes out at 23:00 and eats the next
morning's window.

And a related one: **a failed pass must not consume the window.** The
runner only records `last_run` after a clean pass, so a job that couldn't
fetch at 07:00 retries at 07:15 rather than skipping the day. That's why
the error contract is `raise` — swallowing the error would look like
success.

## One bad job must not take down the daemon

Sources change their HTML. APIs get retired with a month's notice you
didn't read. The job you added at midnight has a typo in it.

Every job call is wrapped, and every source loop inside a job should be
too. A hub that dies at 3am because one feed went away is worse than no
hub, because you stop trusting it — and then you stop noticing when the
*other* jobs stop as well.

The other half of this is that failures must be *visible*. A job quietly
erroring for a week looks exactly like a healthy quiet job. That's the
whole reason the `runs` table records failures and the dashboard puts a
red dot on them.

## "Nothing works without keys" is a bug

Clone this repo, run `python -m src.main --run hello --dry-run`, and you
get a real message printed to your terminal. No `.env`, no accounts, no
hardware.

That's worth protecting, for three reasons that turn out to be the same
reason:

- You can see the whole thing work before deciding to set anything up.
- The test suite runs offline, in CI, on a laptop in a tunnel.
- The state a fresh fork is in — empty `.env`, nothing configured — is a
  state that's actually tested, rather than one nobody has been in since
  the first commit.

So: every optional dependency degrades rather than fails. No channel
configured means messages go to the log. `console` is the floor the
router can always fall back to.

## Decisions in git, secrets in `.env`

`config.yaml` holds every decision — which jobs are on, when they run,
what thresholds matter to you — and it's committed. `git log config.yaml`
becomes the story of how your hub got tuned, which is genuinely useful
six months later when you're wondering why you set something to 40.

`.env` holds every secret, and nothing reads it except the channel that
needs it. Jobs never touch credentials.

The dividing line is worth keeping crisp when you extend this: if you'd
be happy for it to appear in a screenshot, it's config.

## One SQLite file per job

It would be simpler to share one database. It would also mean a schema
change to one job can lock or corrupt another, and that deleting a job's
state means a careful `DELETE`.

Separate files cost nothing and mean:

- Jobs can't interfere with each other's writes.
- Deleting a job is `rm hub/data/<job>.db`.
- The dashboard can mount the whole directory read-only and enumerate
  jobs by looking at what's on disk.

The state itself matters more than it looks. **It's the difference
between a hub and a cron job that spams you**: it's how the hub knows
what it has already told you. Lose `hub/data/` and every job re-notifies
you about everything. That's why it's a host volume, not a container
layer.

## Jobs never name a channel

The version this was distilled from was welded to one messaging app.
Every job imported it directly, dry-run was special-cased inside it, and
switching channels would have meant touching every job.

Now jobs call `ctx.send()` and the router decides, from `config.yaml`,
where it goes. Switching from Discord to Telegram is one line. Sending
digests to email and alerts to your phone is two.

That inversion is most of what makes this forkable at all: your hub's
channels are a config decision, not a code decision.

## The dashboard is read-only, and that's enforced

The status page mounts the data volume **read-only** in `docker-compose.yml`.
Not "doesn't write" by convention — *can't*.

It's the thing you leave open on a tablet in the kitchen and hand to
whoever asks whether it's working. It should be impossible for it to
corrupt what it's reporting on. It also shares no code with the hub: the
contract between the two images is the SQLite schema, so either can be
rebuilt or rewritten without the other noticing.

## Small things that were worth doing once

- **Split long messages, don't truncate.** Every channel has a length
  cap. The item you needed is always the one that fell off the bottom.
- **Every HTTP call gets a timeout.** A box that hangs forever on a
  socket read is indistinguishable from a dead one.
- **The file log is DEBUG, and rotates daily.** When a job misbehaves you
  want yesterday's detailed trail, and you won't have thought to turn it
  on in advance.
- **Prefer keyless APIs.** A hub that needs five accounts set up is a hub
  you never finish setting up.
- **Say the decision, not the data.** "Take a jacket", not "14°C". A
  notification you have to interpret is one you start ignoring — which
  brings this back to the first section.

## What's deliberately missing

No web UI for editing config — it's a YAML file you edit and a container
you restart. No plugin system — jobs are Python files. No auth on the
dashboard — it's a LAN page, and if you need it remotely, Tailscale is
twenty minutes and better than anything this repo would ship. No
database beyond SQLite.

Each of those would be a reasonable thing to add to *your* fork if you
want it. None of them is worth carrying by default.
