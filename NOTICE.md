# Sources and dependencies

The CLI wrapper is authored for this project. Comment collection and bounded live-event code were moved from the local social-cli-lab experiment. No account data or credentials are distributed.

Runtime dependency: bilibili-api-python 17.4.2, GPL-3.0-or-later, https://github.com/Nemo2011/bilibili-api. That upstream repository has ceased maintenance. The present package does not vendor it. aiohttp is a separately installed Apache-2.0 dependency.

The experiment used bilibili-cli 0.6.2 (https://github.com/public-clis/bilibili-cli, Apache-2.0) to establish the existing local credential format. This product does not depend on or copy the upstream CLI implementation, and does not include its login flow.

This project is licensed under GPL-3.0-or-later; see LICENSE. It is an independent project, not an official Bilibili SDK or service.
