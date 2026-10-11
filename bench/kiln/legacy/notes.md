# legacy notes

(personal notes, newest at the bottom, not cleaned up. may be wrong.)

## 2024-11-06

kiln k1 thermocouple check done today. compared with the handheld probe at 1000 C setpoint:
k1 display says 1000, probe says 1009. so k1 reads 9 C LOW at 1000 (type K, old one).
at 600 C the gap was only 4 C. need to write the offset down somewhere. TODO tell owner
- dashboard tablet charger replaced.
- booking site slow after lunch. nothing found. gone by itself.

## 2024-11-07

tried 'Swiftbox' courier for shipping glazed pieces to the two online customers. 3 of 5 parcels
arrived chipped, their packing rules are useless for ceramics. dropping them, back to the post office.
(no more courier experiments, not worth it)
- dashboard tablet charger replaced.
- typo in the faq: 'bisque' spelled 'bisk'. fixed.
- thermocouple on k2 zone 2 replaced, calibrated against the reference.

## 2024-11-07

booking site: port 5000 on web-srv right now, http only. owner wants https. maybe put something in front?
chatbot on 8000. scheduler status 7400. remember these!!
ssh goes through jump-gw port 2222 then hop. annoying but ok
- restarted ChatBot, no reason.

## 2024-11-12

backup idea: stop BookingWeb + ChatBot at 03:00, Copy-Item bookings.db to \\studio-srv\share\backups,
start them again. keep 7 days. simple. works on my test. (will need to check what happens if copy hangs)
- operator asked how to see if a firing is running -> status page on 7400 /status
- dashboard tablet charger replaced.
- typo in the faq: 'bisque' spelled 'bisk'. fixed.

## 2024-11-17

glaze test tiles: numbering scheme is G-<year>-<seq>, e.g. G-2025-014. keep tiles in the blue crate under
the window shelf. the white crate is for failed ones, do NOT mix
- ping web-srv: 3 ms. fine.

## 2024-11-17

PS> Get-ScheduledTask | ? State -eq Ready | select TaskName,State
TaskName            State
--------            -----
KilnScheduler       Ready
KilnTelemetryPoll   Ready
GlazeInventorySync  Ready
NightlyBackup       Ready
- thermocouple on k2 zone 2 replaced, calibrated against the reference.
TODO: check disk

## 2024-11-18

reminder mails: sent via smtp on mail.emberline.example port 25 (no auth) for now. owner says move to 587 later.
TODO: tls. TODO: ask hosting about spf record
- booking site slow after lunch. nothing found. gone by itself.
TODO: test restore

## 2024-11-20

kiln scheduler keeps dying?? checked event log, nothing. restarted it by hand. third time this month.
no idea. maybe memory. maybe the python version. will watch.
- dashboard tablet charger replaced.

## 2024-11-22

price list (2025): wheel intro 55, handbuilding 48, glaze day 30, open studio hour 12.
owner wants to raise wheel to 60 in the new year
- tested the door alarm. works. still quiet.
TODO: ask owner

## 2024-11-23

note to self: never edit a .kiln file directly on the server. edit here, copy over. last time I fixed a
typo on the server and forgot the repo copy, then overwrote it on the next copy. lost 20 minutes
- restarted ChatBot, no reason.

## 2024-11-23

disk space check on web-srv:
Filesystem   Size  Used  Avail
D:           200G  131G   69G
c:           100G   62G   38G
fine for now. log folder is the biggest. should probably rotate. TODO
- operator asked how to see if a firing is running -> status page on 7400 /status
- restarted ChatBot, no reason.

## 2024-11-28

cone 6 notes: the glaze_melt ramp 150/h to 1222 then hold 10 is what the owner likes. do not touch.
cone 04 bisque goes to 1060 hold 15. slow through quartz inversion (573) !!
- asked owner about vouchers. 'later'.

## 2024-11-30

idea: sticker label printer for shelf labels. print-srv port 9100. got it printing a test page once.
abandoned, the labels peel off in the kiln room heat. nobody used it
- operator asked how to see if a firing is running -> status page on 7400 /status
- asked owner about vouchers. 'later'.
- restarted ChatBot, no reason.

## 2024-12-01

wifi in the studio is flaky near the kiln room, the tablet loses the dashboard page. moved the access point
to the hallway ceiling. better.
- ran the profile check on all profiles, all ok.
- restarted ChatBot, no reason.

## 2024-12-01

checked with operator: refunds are done by hand in the provider dashboard for now. no code. owner approves
each one by text message. keep a list in the journal
- owner approved the new glaze day pricing.
TODO: rotate logs

## 2024-12-01

copied from the vendor email:
  'The ProFire 7 supports up to 16 programs. Use register 40002 for setpoint.'
didn't try it yet
- owner approved the new glaze day pricing.
- typo in the faq: 'bisque' spelled 'bisk'. fixed.

## 2024-12-03

half thought: what if the scheduler could pre-heat the kiln so the first class firing starts warm?
no. bad for the elements and the power bill. skip.
- updated python packages on dev-ws. nothing broke.
- owner approved the new glaze day pricing.
- operator asked how to see if a firing is running -> status page on 7400 /status

## 2024-12-03

smtp_pass=Tn5!wK8cRe <!-- memcrumbs:allow -->
- checked backups folder, 7 files present.
TODO: ask owner

## 2024-12-06

python version on studio-srv is 3.10, web-srv 3.11. keep code compatible with both?? the | type unions need 3.10.
ok both fine
- cleaned the kiln shelves, wash applied (kiln wash 50/50 alumina and kaolin).
TODO: ask owner

## 2024-12-09

telemetry: scheduler broadcasts temps on UDP 7411 every 10 s. the dashboard listens. works on the lan only.
- checked backups folder, 7 files present.

## 2024-12-10

power cut last night 02:10-02:40. kiln k2 was idle, thank god. the servers came back on their own.
the scheduler task did NOT restart until I logged in?? check the 'at startup' trigger
- updated python packages on dev-ws. nothing broke.

## 2024-12-11

TODO list (messy):
- [ ] rotate logs
- [ ] write down thermocouple offsets
- [ ] test restore of bookings.db (never done!)
- [x] new shelf labels
- [ ] ask owner about card terminal
- restarted ChatBot, no reason.
TODO: fix reminder time

## 2024-12-12

PS> ssh jump-gw -p 2222
Welcome.
PS> ssh studio-srv
(works, then I forget which server I am on. set the prompt colour)
- ran the profile check on all profiles, all ok.
- thermocouple on k2 zone 2 replaced, calibrated against the reference.

## 2024-12-15

the chatbot gives wrong class times sometimes. the FAQ file has the old timetable. need to re-edit faq.json
and restart the bot. just restart it. TODO make it reload by itself
- owner approved the new glaze day pricing.
- ping web-srv: 3 ms. fine.
- operator asked how to see if a firing is running -> status page on 7400 /status
TODO: write down offsets

## 2024-12-16

supplier call: clay body 'Stone 5' backordered 3 weeks. use 'Stone 7' meanwhile, fires the same at cone 6
but a bit darker. told the students.
- cleaned the kiln shelves, wash applied (kiln wash 50/50 alumina and kaolin).
- tested the door alarm. works. still quiet.
- asked owner about vouchers. 'later'.
TODO: fix reminder time

## 2024-12-19

test of restore: copied bookings.db from the backup folder over the live one with the site stopped.
site came back fine. took 4 minutes. (did not run integrity check, meh)
- asked owner about vouchers. 'later'.
- dashboard tablet charger replaced.

## 2024-12-21

cert for the site: bought a 1-year cert, installed by hand in the proxy folder. calendar reminder set for
renewal 2 weeks before. proxy config lives in C:\proxy\conf
- checked backups folder, 7 files present.

## 2024-12-22

kiln door alarm: relay on COM5, DoorAlarmRelay script polls it. beeps in the office. the beep is too quiet.
- operator asked how to see if a firing is running -> status page on 7400 /status
- ordered 20 kg of cobalt-free blue stain.
- asked owner about vouchers. 'later'.

## 2024-12-25

invoice export: accountant wants csv by 04:00 daily. InvoiceSync is a python script, runs at 03:10. fine.
- owner approved the new glaze day pricing.
- tested the door alarm. works. still quiet.
- restarted ChatBot, no reason.
TODO: check disk

## 2024-12-28

random: the owner says never store the card payment key in files. use env var. ok. set with setx /M.
- thermocouple on k2 zone 2 replaced, calibrated against the reference.
- restarted ChatBot, no reason.
- ordered 20 kg of cobalt-free blue stain.
TODO: write down offsets

## 2025-01-02

idea dump:
 * gift vouchers on the site
 * waitlist for full classes
 * show kiln status to students ('your pots are in the glaze firing, done Thursday')
 * email when firing done
none started
- operator asked how to see if a firing is running -> status page on 7400 /status
- dashboard tablet charger replaced.
TODO: rotate logs

## 2025-01-03

debug session booking 'held' status never clears. the StaleHoldSweeper idea: a task every 10 min that
sets expired holds to void. wrote it. hold is 10 minutes. works.
- thermocouple on k2 zone 2 replaced, calibrated against the reference.
- owner approved the new glaze day pricing.
- restarted ChatBot, no reason.

## 2025-01-05

cone 10 reduction on k3 -- k3 does not exist yet. the owner is shopping for a second ProFire 7. maybe autumn.
- tested the door alarm. works. still quiet.
- asked owner about vouchers. 'later'.
- booking site slow after lunch. nothing found. gone by itself.

## 2025-01-06

the old scheduler ran as a real service with nssm. replaced by a scheduled task because nssm update broke
after the windows update. scheduled task 'At startup' + run whether logged on or not.
- dashboard tablet charger replaced.

## 2025-01-11

FOLLOW UP from monday: owner wants approval step before deploying the site. ok, will ask every time.
- checked backups folder, 7 files present.

## 2025-01-11

timezone confusion again. server clock is UTC, owner thinks in local. the reminder said 16:00 but
class is 18:00... look at it later
- ordered 20 kg of cobalt-free blue stain.
- ran the profile check on all profiles, all ok.
- owner approved the new glaze day pricing.

## 2025-01-11

command output pasted:
> python -m scheduler.profile_loader --check profiles/cone6_glaze.kiln
OK cone6_glaze on k2: 3 segments
(older version, only three segments then)
- tested the door alarm. works. still quiet.
- checked backups folder, 7 files present.

## 2025-01-16

deploy of website, my way: zip, scp to web-srv, unzip over the live folder, restart BookingWeb. takes 5 min.
no rollback besides the zip on my laptop
- updated python packages on dev-ws. nothing broke.

## 2025-01-17

brainstorm: could we use postgres? everyone says sqlite will not scale. we have 30 bookings a week.
- dashboard tablet charger replaced.
- restarted ChatBot, no reason.
- operator asked how to see if a firing is running -> status page on 7400 /status

## 2025-01-17

Studio hours: Tue-Sat 10-18, Sunday workshops by booking. emails reply within one working day.
- checked backups folder, 7 files present.
- thermocouple on k2 zone 2 replaced, calibrated against the reference.
- typo in the faq: 'bisque' spelled 'bisk'. fixed.

## 2025-01-20

inventory sync reads supplier csv from \\studio-srv\share\supplier\stock.csv. file appears around midnight. if
missing job just exits silently. TODO log that
- restarted ChatBot, no reason.
TODO: rotate logs

## 2025-01-21

TODO: figure out why the telemetry poll sometimes writes two rows with the same timestamp. harmless?
- ran the profile check on all profiles, all ok.
- operator asked how to see if a firing is running -> status page on 7400 /status
- tested the door alarm. works. still quiet.

## 2025-01-23

firing log excerpt (copied):
  10:00  zone1 300 C  zone2 294 C  sp 304
  11:00  zone1 345 C  zone2 342 C  sp 347
  12:00  zone1 422 C  zone2 417 C  sp 432
  13:00  zone1 499 C  zone2 501 C  sp 500
  14:00  zone1 566 C  zone2 566 C  sp 566
- restarted ChatBot, no reason.
- booking site slow after lunch. nothing found. gone by itself.
- updated python packages on dev-ws. nothing broke.

## 2025-01-24

firing log excerpt (copied):
  10:00  zone1 157 C  zone2 162 C  sp 159
  11:00  zone1 216 C  zone2 215 C  sp 226
  12:00  zone1 290 C  zone2 296 C  sp 291
  13:00  zone1 349 C  zone2 352 C  sp 356
  14:00  zone1 417 C  zone2 411 C  sp 425
- checked backups folder, 7 files present.
- cleaned the kiln shelves, wash applied (kiln wash 50/50 alumina and kaolin).

## 2025-01-24

firing log excerpt (copied):
  10:00  zone1 267 C  zone2 269 C  sp 268
  11:00  zone1 308 C  zone2 308 C  sp 311
  12:00  zone1 356 C  zone2 350 C  sp 359
  13:00  zone1 393 C  zone2 396 C  sp 393
  14:00  zone1 429 C  zone2 425 C  sp 437
- typo in the faq: 'bisque' spelled 'bisk'. fixed.
- dashboard tablet charger replaced.
- ordered 20 kg of cobalt-free blue stain.

## 2025-01-25

PS> Get-Counter '\Processor(_Total)\% Processor Time' -SampleInterval 2 -MaxSamples 3
  cpu 19 %   mem free 3210 MB
  cpu 33 %   mem free 2555 MB
  cpu 7 %   mem free 2741 MB
- thermocouple on k2 zone 2 replaced, calibrated against the reference.
- cleaned the kiln shelves, wash applied (kiln wash 50/50 alumina and kaolin).
- booking site slow after lunch. nothing found. gone by itself.
TODO: test restore

## 2025-01-30

- asked owner about vouchers. 'later'.
- cleaned the kiln shelves, wash applied (kiln wash 50/50 alumina and kaolin).

## 2025-02-04

PS> Get-Counter '\Processor(_Total)\% Processor Time' -SampleInterval 2 -MaxSamples 3
  cpu 24 %   mem free 1756 MB
  cpu 29 %   mem free 3767 MB
  cpu 31 %   mem free 3837 MB
- operator asked how to see if a firing is running -> status page on 7400 /status
- updated python packages on dev-ws. nothing broke.
- ping web-srv: 3 ms. fine.

## 2025-02-05

- cleaned the kiln shelves, wash applied (kiln wash 50/50 alumina and kaolin).
- thermocouple on k2 zone 2 replaced, calibrated against the reference.

## 2025-02-06

PS> Get-Counter '\Processor(_Total)\% Processor Time' -SampleInterval 2 -MaxSamples 3
  cpu 6 %   mem free 2910 MB
  cpu 28 %   mem free 1952 MB
  cpu 22 %   mem free 4580 MB
- ran the profile check on all profiles, all ok.
- ping web-srv: 3 ms. fine.

## 2025-02-06

- ping web-srv: 3 ms. fine.
- owner approved the new glaze day pricing.
TODO: check disk

## 2025-02-07

- operator asked how to see if a firing is running -> status page on 7400 /status
- typo in the faq: 'bisque' spelled 'bisk'. fixed.

## 2025-02-12

PS> Get-Counter '\Processor(_Total)\% Processor Time' -SampleInterval 2 -MaxSamples 3
  cpu 19 %   mem free 1723 MB
  cpu 34 %   mem free 3481 MB
  cpu 25 %   mem free 3166 MB
- dashboard tablet charger replaced.
- ran the profile check on all profiles, all ok.
- restarted ChatBot, no reason.

## 2025-02-13

- typo in the faq: 'bisque' spelled 'bisk'. fixed.

## 2025-02-16

firing log excerpt (copied):
  10:00  zone1 193 C  zone2 195 C  sp 197
  11:00  zone1 253 C  zone2 254 C  sp 259
  12:00  zone1 297 C  zone2 298 C  sp 302
  13:00  zone1 363 C  zone2 368 C  sp 369
  14:00  zone1 449 C  zone2 446 C  sp 452
- updated python packages on dev-ws. nothing broke.
- thermocouple on k2 zone 2 replaced, calibrated against the reference.
- checked backups folder, 7 files present.

## 2025-02-18

firing log excerpt (copied):
  10:00  zone1 213 C  zone2 210 C  sp 215
  11:00  zone1 290 C  zone2 288 C  sp 291
  12:00  zone1 367 C  zone2 363 C  sp 371
  13:00  zone1 402 C  zone2 401 C  sp 412
  14:00  zone1 462 C  zone2 464 C  sp 468
- updated python packages on dev-ws. nothing broke.

## 2025-02-19

- typo in the faq: 'bisque' spelled 'bisk'. fixed.
TODO: rotate logs

## 2025-02-24

firing log excerpt (copied):
  10:00  zone1 163 C  zone2 166 C  sp 172
  11:00  zone1 194 C  zone2 191 C  sp 202
  12:00  zone1 244 C  zone2 245 C  sp 248
  13:00  zone1 301 C  zone2 305 C  sp 307
  14:00  zone1 332 C  zone2 337 C  sp 334
- updated python packages on dev-ws. nothing broke.
- ran the profile check on all profiles, all ok.
- restarted ChatBot, no reason.

## 2025-02-25

- owner approved the new glaze day pricing.
- tested the door alarm. works. still quiet.
TODO: check disk

## 2025-02-28

- cleaned the kiln shelves, wash applied (kiln wash 50/50 alumina and kaolin).
TODO: test restore

## 2025-03-03

- booking site slow after lunch. nothing found. gone by itself.
- thermocouple on k2 zone 2 replaced, calibrated against the reference.
- updated python packages on dev-ws. nothing broke.
TODO: ask owner

## 2025-03-08

- operator asked how to see if a firing is running -> status page on 7400 /status

## 2025-03-13

firing log excerpt (copied):
  10:00  zone1 288 C  zone2 283 C  sp 291
  11:00  zone1 375 C  zone2 376 C  sp 379
  12:00  zone1 462 C  zone2 466 C  sp 467
  13:00  zone1 502 C  zone2 504 C  sp 504
  14:00  zone1 542 C  zone2 536 C  sp 546
- dashboard tablet charger replaced.
- cleaned the kiln shelves, wash applied (kiln wash 50/50 alumina and kaolin).

## 2025-03-13

firing log excerpt (copied):
  10:00  zone1 271 C  zone2 269 C  sp 275
  11:00  zone1 331 C  zone2 335 C  sp 332
  12:00  zone1 385 C  zone2 390 C  sp 386
  13:00  zone1 419 C  zone2 423 C  sp 422
  14:00  zone1 467 C  zone2 462 C  sp 477
- typo in the faq: 'bisque' spelled 'bisk'. fixed.
- booking site slow after lunch. nothing found. gone by itself.
- updated python packages on dev-ws. nothing broke.

## 2025-03-14

firing log excerpt (copied):
  10:00  zone1 258 C  zone2 262 C  sp 267
  11:00  zone1 313 C  zone2 315 C  sp 323
  12:00  zone1 344 C  zone2 341 C  sp 348
  13:00  zone1 419 C  zone2 425 C  sp 429
  14:00  zone1 500 C  zone2 506 C  sp 503
- cleaned the kiln shelves, wash applied (kiln wash 50/50 alumina and kaolin).
- restarted ChatBot, no reason.
- tested the door alarm. works. still quiet.

## 2025-03-19

- cleaned the kiln shelves, wash applied (kiln wash 50/50 alumina and kaolin).
TODO: check disk

## 2025-03-19

- updated python packages on dev-ws. nothing broke.
- ran the profile check on all profiles, all ok.
- ordered 20 kg of cobalt-free blue stain.

## 2025-03-19

PS> Get-Counter '\Processor(_Total)\% Processor Time' -SampleInterval 2 -MaxSamples 3
  cpu 6 %   mem free 1975 MB
  cpu 28 %   mem free 3415 MB
  cpu 28 %   mem free 2593 MB
- checked backups folder, 7 files present.

## 2025-03-22

firing log excerpt (copied):
  10:00  zone1 348 C  zone2 353 C  sp 356
  11:00  zone1 385 C  zone2 388 C  sp 394
  12:00  zone1 430 C  zone2 430 C  sp 437
  13:00  zone1 476 C  zone2 481 C  sp 486
  14:00  zone1 527 C  zone2 528 C  sp 535
- dashboard tablet charger replaced.
- checked backups folder, 7 files present.
TODO: ask owner

## 2025-03-22

firing log excerpt (copied):
  10:00  zone1 307 C  zone2 302 C  sp 309
  11:00  zone1 341 C  zone2 344 C  sp 346
  12:00  zone1 391 C  zone2 397 C  sp 399
  13:00  zone1 447 C  zone2 448 C  sp 453
  14:00  zone1 513 C  zone2 514 C  sp 521
- owner approved the new glaze day pricing.

## 2025-03-27

- dashboard tablet charger replaced.
TODO: call supplier

## 2025-04-01

firing log excerpt (copied):
  10:00  zone1 244 C  zone2 247 C  sp 244
  11:00  zone1 290 C  zone2 286 C  sp 293
  12:00  zone1 336 C  zone2 331 C  sp 339
  13:00  zone1 398 C  zone2 392 C  sp 407
  14:00  zone1 440 C  zone2 442 C  sp 440
- tested the door alarm. works. still quiet.
- dashboard tablet charger replaced.
- ping web-srv: 3 ms. fine.

## 2025-04-06

PS> Get-Counter '\Processor(_Total)\% Processor Time' -SampleInterval 2 -MaxSamples 3
  cpu 6 %   mem free 4703 MB
  cpu 40 %   mem free 4524 MB
  cpu 13 %   mem free 2908 MB
- dashboard tablet charger replaced.

## 2025-04-07

- typo in the faq: 'bisque' spelled 'bisk'. fixed.
- owner approved the new glaze day pricing.
- booking site slow after lunch. nothing found. gone by itself.

## 2025-04-10

PS> Get-Counter '\Processor(_Total)\% Processor Time' -SampleInterval 2 -MaxSamples 3
  cpu 34 %   mem free 5052 MB
  cpu 9 %   mem free 2807 MB
  cpu 9 %   mem free 4776 MB
- operator asked how to see if a firing is running -> status page on 7400 /status
- ping web-srv: 3 ms. fine.
- thermocouple on k2 zone 2 replaced, calibrated against the reference.
TODO: ask owner

## 2025-04-11

- ordered 20 kg of cobalt-free blue stain.
- thermocouple on k2 zone 2 replaced, calibrated against the reference.
- dashboard tablet charger replaced.
TODO: call supplier

## 2025-04-11

firing log excerpt (copied):
  10:00  zone1 253 C  zone2 253 C  sp 256
  11:00  zone1 341 C  zone2 339 C  sp 341
  12:00  zone1 397 C  zone2 394 C  sp 401
  13:00  zone1 446 C  zone2 452 C  sp 453
  14:00  zone1 507 C  zone2 504 C  sp 508
- operator asked how to see if a firing is running -> status page on 7400 /status
- checked backups folder, 7 files present.
- booking site slow after lunch. nothing found. gone by itself.

## 2025-04-14

- updated python packages on dev-ws. nothing broke.
- thermocouple on k2 zone 2 replaced, calibrated against the reference.
- restarted ChatBot, no reason.

## 2025-04-19

PS> Get-Counter '\Processor(_Total)\% Processor Time' -SampleInterval 2 -MaxSamples 3
  cpu 14 %   mem free 1893 MB
  cpu 21 %   mem free 4223 MB
  cpu 18 %   mem free 4544 MB
- dashboard tablet charger replaced.
- operator asked how to see if a firing is running -> status page on 7400 /status
- updated python packages on dev-ws. nothing broke.

## 2025-04-20

PS> Get-Counter '\Processor(_Total)\% Processor Time' -SampleInterval 2 -MaxSamples 3
  cpu 11 %   mem free 3292 MB
  cpu 24 %   mem free 3940 MB
  cpu 12 %   mem free 2486 MB
- owner approved the new glaze day pricing.
- ran the profile check on all profiles, all ok.

