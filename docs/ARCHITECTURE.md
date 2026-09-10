# Design decisions

Why the boilerplate is shaped the way it is. Useful if you're extending
it; skippable if you just want it running.

## Jobs send nothing most of the time

`run(ctx)` returns nothing, and sending is an explicit call. A job that
reports "everything is fine" every fifteen minutes trains you to ignore
its notifications, at which point it can't reach you when something is
actually wrong.

For alerting jobs, this means alerting on the *crossing* rather than the
state: record the level you last alerted at, and alert again only when it
worsens by a configured step.

## Schedules assume downtime

Power cuts and reboots happen, so schedules store the *last successful
run* and compare it against the window boundary. Two consequences:

- **Catch-up.** A window missed while the box was off fires when it comes
  back.
- **Never twice.** A served window stays served regardless of tick rate.

Counting down from the last run, or asking "has anything been sent in the
last 24 hours", both break — the second one visibly, the first time a
catch-up message goes out at 23:00 and consumes the next morning's window.

Related: a failed pass must not consume the window. `last_run` is written
only after a clean pass, which is why the error contract is `raise` rather
than returning a status — swallowing an error would look like success.

## One failing job doesn't stop the others

Every job call is wrapped. APIs get retired and new jobs have typos in
them; a daemon that exits at 3am stops being trusted, and then you also
stop noticing when other jobs fail.

Failures are recorded in the `runs` table so that a job erroring for a
week looks different from a job that has nothing to report. The dashboard
shows the difference.

## Everything works without credentials

A fresh clone runs, and `--run hello --dry-run` produces real output with
no `.env`. This keeps the test suite offline and CI-friendly, and it means
the state a new user is in — nothing configured — is a state that's
actually tested.

Optional dependencies degrade rather than fail: unconfigured channels are
skipped, and `console` is the fallback the router can always use.

## Config is committed, secrets are not

`config.yaml` holds decisions — which jobs run, when, and how they're
tuned — and is version-controlled. `.env` holds credentials and is read
only by the channel that needs them. Jobs never touch credentials.

Rule of thumb when extending: if you'd be comfortable with it in a
screenshot, it's config.

## One SQLite file per job

Sharing one database would mean a schema change in one job can lock or
corrupt another, and removing a job's state means a careful `DELETE`.
Separate files cost nothing and mean:

- Jobs can't interfere with each other's writes.
- Removing a job is `rm hub/data/<job>.db`.
- The dashboard mounts the directory read-only and enumerates jobs from
  what's on disk.

The state is what distinguishes a hub from a cron job that spams you — it
records what has already been sent. It's a host volume rather than a
container layer for that reason.

## Jobs don't name channels

Jobs call `ctx.send()`; the router reads `config.yaml` and decides. This
makes switching channels a one-line config change, and sending digests to
email while alerts go to your phone a two-line one.

## The dashboard is read-only, enforced

`docker-compose.yml` mounts the data volume `:ro`, so the status page
cannot write to job state — not by convention, but because the mount
forbids it.

It also shares no code with the hub. The contract between the two images
is the SQLite schema, so either can be rebuilt or replaced independently.

## Smaller decisions

- **Split long messages, don't truncate.** Every channel has a length cap.
- **Every HTTP call has a timeout.** A process hung on a socket read is
  indistinguishable from a dead one.
- **The file log is DEBUG and rotates daily.** You want yesterday's detail
  when something misbehaves, and you won't have enabled it in advance.
- **Prefer keyless APIs** in jobs — fewer accounts to set up.
- **Send conclusions, not data.** "Take a jacket", not "14°C".

## Deliberately not included

No web UI for editing config (it's a YAML file and a container restart).
No plugin system (jobs are Python files). No auth on the dashboard (see
[TAILSCALE.md](TAILSCALE.md)). No database beyond SQLite.

Any of these would be reasonable additions to your own fork.
