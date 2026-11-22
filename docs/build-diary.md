# Build diary

Ace Perez · November 2026

Nine days, 22 pull requests, and many things that didn't go as planned. This is a simple description of building Orbit Telemetry (a real-time satellite console using all components of a complete CI/CD pipeline), which was developed for the DevOps course module at ATU Donegal and as a personal project I'll continue improving. The technical details can be found in the [pull requests](https://github.com/ace-perez/orbit-telemetry/pulls?q=is%3Apr+is%3Amerged) and [pipeline history](https://github.com/ace-perez/orbit-telemetry/actions). I have written this version so you will see what happened, and what I learned.

## Saturday 14 Nov to Wednesday 18 Nov: Making the plan

The first design incorporated many features that I decided were too much to implement by the time of my deadline. Therefore, prior to beginning the actual coding phase, I reviewed the grading rubric and eliminated all items that would not impact the final grade: a separate development environment, a simple AWS networking configuration, and three other nice-to-haves (GitOps, HTTPS, and a delivery metrics dashboard) will be implemented after the deadline. All cuts are documented along with the reasoning behind them, therefore none of these cuts happened without documentation.

On Day One there were two smaller than expected challenges. Implementing AWS using the “best” practices resulted in my account being automatically placed into a paid status (which it eventually was – we’ll get to that in Fridays post). Therefore, I created a basic user login with Two-Factor Authentication, and since the pipeline does not use any stored keys. Also, the Kubernetes package manager called Helm, changed the name of the single flag that my deploy relied upon when they made their most recent Major Version update. A minor challenge however it is the reason that each tool has been pinned to an exact version on my laptop, in our Continuous Integration system and on the production server.

## Thursday 19 Nov: the app and the first gates

The app came together fast; I had real orbits for five satellites with a simulated battery and temp for each plus an API. The hard part to figure out was testing it. Testing using real orbital data takes place every two hours. Downloading a 17 mb file is how you compute the Suns location. Internet dependent tests that also rely on your system time will always be flaky. So I made my tests use a static set of satellite data, a dummy clock and a simplified sun calculation. In less than one second, I could run all fifty-one of those tests offline. That’s why having tests run as often as possible is do-able.

That night I had the first of many pipelines running over every pull request. Formatting and lint checkers were included, then the test suite. Lastly, there was a 80% minimum coverage requirement (the app sits at around 97%).

## Friday 20 Nov: security gates, containers, Kubernetes and AWS

Longest day: four phases and the pipeline starts to pay off.

- **i had wrong evidence.** i had a screen shot of a failed test blocking a merge. However, the policy that forces checks to pass has never been enabled, therefore, the block in my screen shot was advisory. I fixed the policy, checked it, and replayed the demo. Lesson: check if the control is enabled, not if you ran the command.
- **Trivy (the security scanner) has been hacked.** as i was deciding how to use Trivy in CI, i found that the official github actions for Trivy have been compromised since March 2026 to siphon off secrets from your pipelines. I've switched to using the tool directly into each environment; pinned and checksum verified. Every single action in this pipeline is pinned to an exact commit.
- **Bandit caught my own real mistake.** Bandit said that the app listened on all network interfaces by default. I fixed the default setting rather than disabling the flag.
- **SonarQube didn't catch it though.** SonarQube did not catch this issue though because SonarQube can only judge changes made to new lines. I also took advantage of this behavior when doing other testing.
- **the package manager would not allow my "vulnerability on purpose" demo.** the version of the old library that i selected to show the vulnerability blocker wouldn't install properly with any modern packages. Another older library worked fine, and the build failed just as i wanted it too.
- **an online course project was squatting on my ports.** the local stack will not start up because there are still containers running from an online course on top of the same ports that my app wants to listen on, and they responded back to my test with another application's reply. I identified the offending container and stopped it. I also learned that checking which service is responding to requests is important.
- **real vulnerabilities were identified in the container scan.**, but they weren't in my code, rather in base image that I built upon. I upgraded the affected system library and uninstalled the tool that my app does not use, rather than ignoring the issues identified by the scans.
- **even with all checks green, comments from the scanner blocked a merge.**, because our repository configuration requires that all reviewers resolve their comments before merging. Each one received a review and a written explanation — that's part of what comments should do anyway.

Then AWS. I had planned for free credits, but the account is on a paid plan without any credits available, so every hour of server usage costs money. I evaluated my options and chose a Graviton based arm server for cost reasons, and then put my image builds on arm runner so that my tests are built with images that run in production. A $20 alert monitors the AWS billing.

The first actual deployment failed: AWS rejected github's login credentials. Github had quietly changed the format of its identity tokens for repositories created after July 2026 and my repo was one of those. Once I compared what AWS was expecting with what was in the token's payload, I needed to add just two lines to make it work. Before the end of the day, every successful merge automatically deploys itself, and verifies the site from outside.

## Saturday 21 Nov: the safety net with a hole

Saturday was monitoring: Prometheus collecting numbers, Grafana drawing them, Loki keeping the logs, alerts going to a Discord channel, and a target of 99.5% of requests succeeding. The headline feature was a post-deploy check: after every release, wait two and a half minutes, look at the real error rate, and roll back automatically if more than 5% of requests are failing.

It was a day of things not being what they seemed:

- **The right password kept failing.** Grafana rejected a password I could prove was correct. After a round of resetting things, the cause was that another Grafana, from the online course, was running on the same port, and my browser was quietly logging in to that one. One request to a health page that reports its version settled it.
- **A green pipeline that deployed nothing.** I had switched deployments off overnight to save money and forgot to switch them back on. The deploy step was skipped, and a skipped step counts as a success. Green does not mean it happened; I check the release history now.
- **Charts that said "No data" on a healthy service.** With no errors ever served, there was no error count at all, and "nothing" divided by anything is still nothing. One small change makes "no errors" read as zero, while "no traffic" still reads as no data.

Then the real test. I deliberately shipped a release that failed 30% of requests, expecting the rollback. It went straight through. The failed requests were being recorded under a label my check was not looking at, so as far as the check knew, everything was fine. This is the most useful thing that happened all week: a safety net nobody has tested is a guess. I put the service back first, fixed the labelling, added a test that fails on the old behaviour, and ran the demo again. This time the check saw 30% errors, rolled back on its own, turned the pipeline red and posted to Discord.

And it caught one more of my mistakes without being asked. My first attempt to undo the demo merged with no actual change in it (a branch made from the wrong starting point), which redeployed the broken setting. The check rolled that back too, and I only spotted what had happened in the release history afterwards.

The evening was the fun part: the mission console, a 3D globe built from a design mock-up, showing where each satellite is, where it will pass over the next three orbits, and which half of the Earth is in darkness. I checked it against an independent ISS tracker: the two positions matched within a fifth of a degree. A last security pass upgraded a system library with 13 known issues before the release.

## Sunday 22 Nov: release and video

Today's Plan: Tag v1.0.0 of the project, Finish README and Screenshots, Record Demo. 

Decision Made on Saturday Evening: Researching and building (HTTPS) , Satellite Passes for Dublin and Live Space Weather from NOAA was done, however, this is being pushed back until after the deadline because releasing three additional features one night prior to a recording session could possibly ruin the entire demo as the student will not be using all of these features for their grade.

## What I would tell myself on day one

1. **Prove the safety net works.** A missed step in process, an applied but ignored policy or an empty merge can look like "success." Always check results to see that it has been completed (the Release History, the Live Version, the actual configuration).
2. **Green does not mean you are done.** There are many ways to succeed when testing your rollback, but they don’t always result in a working product. An overlooked task, an unapplied rule, or an empty merge can look fine during testing; however, those will show up once you review the final results: the release history, the live site, and actual settings. 
3. **The majority of risks I encountered came from outside of my app code.** The Base Image, a modified Scanner Plugin, a customized Login Format, a Shared Port, etc... Determining pinned versions for everything I used; Scanning what actually shipped and reviewing Changelogs were more important than writing a single line of app code.
4. **Repair, then explain why.** All of the findings received either a decision (whether to repair), along with a reason (why); none of them received a "silent ignore". Those decisions eventually turned into this diary and our report. 
5. **Plan to cut scope early on — and on purpose.** Cutting the scope by half on day one allowed me to complete the critical tasks that needed to be completed correctly, while allowing time to build out additional features and test them properly.