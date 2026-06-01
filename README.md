# Baselines for Confluence — App-Specific Performance Tests

This branch adapts the toolkit to load-test the **Baselines for Confluence**
(OBSS) Data Center app through the JMeter `standalone_extension` hook.
The rest of the toolkit is unchanged; everything described below is additive
and self-skips when the app weight is `0`, so the branch is safe to use even
for non-app runs.

## What this branch changes

- **`app/jmeter/confluence.jmx`** — adds a `baselines` CSV DataSet and, inside
  `standalone_extension`, six weighted app-specific transactions:
  `bsl_view_baseline`, `bsl_browse`, `bsl_compare_baselines`,
  `bsl_create_delete`, `bsl_export_pdf`, `bsl_export_csv`. Each transaction is
  individually labelled in the report. Weighting is done with nested
  `ThroughputController`s (percent-executions): 30 / 30 / 15 / 10 / 10 / 5.
- **`app/util/confluence/prepare_baseline_data.py`** — a seed script that
  follows the same conventions as `confluence_prepare_data.py`. It reads
  `CONFLUENCE_SETTINGS`, walks `datasets/confluence/pages.csv`, resolves the
  numeric space id for each space, and creates two `version-based` baselines
  (`perf-seed-1`, `perf-seed-2`) per space via
  `POST /rest/baseline/1.0/baselineService/createBaseline`. It then writes
  `datasets/confluence/baselines.csv` with the columns JMeter expects:
  `bsl_space_key,bsl_space_id,bsl_page_id,bsl_baseline1,bsl_baseline2`.
  The script self-skips when `standalone_extension: 0`.
- **`app/confluence.yml`** — one new line in `services.prepare`, right after
  `confluence_prepare_data.py`, so the seed runs automatically on every
  `bzt` invocation:
  ```yaml
  - python util/confluence/prepare_baseline_data.py
  ```
- **`app/util/confluence/PERF_BASELINES_README.md`** — detailed reference
  (Turkish) covering action design, troubleshooting and limits.

## How to run the tests

1. **Clone the fork and switch to this branch.**
   ```bash
   git clone https://github.com/OBSS-Apps/dc-app-performance-toolkit.git
   cd dc-app-performance-toolkit
   git checkout baseline-for-confluence
   ```

2. **Make sure the prerequisites are met on the target instance:**
   - The **Baselines for Confluence** app is installed and **licensed** (the
     license must not be expired — every Baselines REST endpoint enforces it).
   - The instance is **not** in read-only mode (create / delete / compare
     would otherwise return 403).
   - Baselines admin permission groups are left unrestricted (default), or
     the toolkit's `performance_*` users are members of the configured
     view / edit / delete / export groups.

3. **Configure `app/confluence.yml`** for your environment. The keys you
   typically touch are all in `settings.env`:
   - `application_hostname`, `application_protocol`, `application_port`,
     `application_postfix` — point at your Confluence DC.
   - `admin_login` / `admin_password` — used by both the standard prepare
     and by the Baselines seed script.
   - `standalone_extension` — share of total load that the six Baselines
     transactions take.
     - `100` — isolate just the new actions (smoke test the branch).
     - `5`–`10` — realistic mixed run alongside the stock Confluence actions.
     - `0` — disable; the seed script will self-skip on prepare.

4. **Pick the Run and toggle the seed line.** Marketplace DC compliance
   evaluates the app across **five runs**; the Baselines data seed script
   (`prepare_baseline_data.py`) must only execute for the last three.
   Toggle one line in `app/confluence.yml` -> `services` -> `prepare`
   and the `standalone_extension` weight per the table below:

   | Run | Confluence instance state | Seed line | `standalone_extension` |
   |---|---|---|---|
   | **Run 1** | Baselines app **not installed** | commented out | `0` |
   | **Run 2** | App installed, **no app data** | commented out | `0` |
   | **Run 3** | App installed, **with app data** | enabled | e.g. `5`–`10` |
   | **Run 4** | Same as Run 3 (repeat) | enabled | same as Run 3 |
   | **Run 5** | Same as Run 3 (repeat) | enabled | same as Run 3 |

   - For **Run 1**, the script would otherwise call `createBaseline`
     against a plugin endpoint that does not exist (app not installed) and
     abort the prepare phase. Commenting it out is mandatory.
   - For **Run 2**, the run must measure the cost of merely *installing*
     the app; pre-creating baselines would inject data and invalidate the
     comparison. Commenting it out is mandatory.
   - For **Runs 3, 4 and 5**, leave the line uncommented so the script
     seeds two `version-based` baselines per space and writes
     `baselines.csv`. Use the same configuration across Runs 3–5 so the
     three samples are comparable.

   ```yaml
   # app/confluence.yml — services -> prepare
       prepare:
         - python util/pre_run/environment_checker.py
         - python util/pre_run/environment_compliance_check.py confluence
         - python util/data_preparation/confluence_prepare_data.py
   #     - python util/confluence/prepare_baseline_data.py   # Runs 1 & 2: commented out · Runs 3-5: uncommented
   ```

5. **Run the toolkit** with the dockerized runner that ships with the
   toolkit (preferred over a plain `bzt` invocation — pins dependencies,
   JMeter version and the agent image):

   ```bash
   export ENVIRONMENT_NAME=your_environment_name

   docker run --pull=always --env-file ./app/util/k8s/aws_envs \
     -e REGION=us-east-2 \
     -e ENVIRONMENT_NAME=$ENVIRONMENT_NAME \
     -v "/$PWD:/data-center-terraform/dc-app-performance-toolkit" \
     -v "/$PWD/app/util/k8s/bzt_on_pod.sh:/data-center-terraform/bzt_on_pod.sh" \
     -it atlassianlabs/terraform:2.9.21 bash bzt_on_pod.sh confluence.yml
   ```

   During `prepare`, the toolkit:
   1. runs `environment_checker.py` / `environment_compliance_check.py`,
   2. runs `confluence_prepare_data.py` (standard datasets — always),
   3. runs `prepare_baseline_data.py` **only when the line above is
      uncommented** (Runs 3–5). When it runs and `standalone_extension > 0`,
      it seeds two baselines per space and writes `baselines.csv`;
      otherwise it self-skips.

   The JMeter run then exercises the `bsl_*` transactions (Runs 3–5) or
   only the core Confluence transactions (Runs 1–2).

6. **Inspect results** under `app/results/confluence/<timestamp>/`:
   - `bzt.log` — confirms the seed step ran (or was skipped) and reports
     per-space outcomes.
   - `kpi.jtl` and the aggregate report — look for the `bsl_*` transaction
     labels alongside the core Confluence transactions (present only for
     Runs 3–5).

## Per-machine settings that are intentionally **not** committed here

So this branch stays reusable across machines, the following are left to
your local `confluence.yml`: `application_hostname`, `admin_login`,
`admin_password`, the action-weight tuning block, the `standalone_extension`
value, and anything under `app/util/k8s/` and `app/reports_generation/`.
Set them locally before running; do not commit them to this branch.

---

# Data Center App Performance Toolkit 
The Data Center App Performance Toolkit extends [Taurus](https://gettaurus.org/) which is an open source performance framework that executes JMeter and Selenium.

This repository contains Taurus scripts for performance testing of Atlassian Data Center products: Jira, Jira Service Management, Confluence, Bitbucket and Crowd.

## Supported versions
* Supported Jira versions: 
    * Jira [Long Term Support release](https://confluence.atlassian.com/enterprise/atlassian-enterprise-releases-948227420.html): `10.3.15`, `11.3.1`

* Supported Jira Service Management versions: 
    * Jira Service Management [Long Term Support release](https://confluence.atlassian.com/enterprise/atlassian-enterprise-releases-948227420.html): `10.3.15`, `11.3.1`
    
* Supported Confluence versions:
    * Confluence [Long Term Support release](https://confluence.atlassian.com/enterprise/atlassian-enterprise-releases-948227420.html): `9.2.13`, `10.2.2`

* Supported Bitbucket Server versions:
    * Bitbucket Server [Long Term Support release](https://confluence.atlassian.com/enterprise/atlassian-enterprise-releases-948227420.html): `8.19.24`, `9.4.12` and `10.0.1` Platform release

* Supported Crowd versions:
    * Crowd [release notes](https://confluence.atlassian.com/crowd/crowd-release-notes-199094.html): `7.1.3`
  
* Supported Bamboo versions:
    * Bamboo [Long Term Support release](https://confluence.atlassian.com/bamboo/bamboo-release-notes-671089224.html): `10.2.14`
  
## Support
In case of technical questions, issues or problems with DC Apps Performance Toolkit, contact us for support in the [community Slack](https://go.atlassian.com/dcapt-community-slack) **#data-center-app-performance-toolkit** channel.

## Installation and set up

#### Dependencies
* Python 3.10 - 3.13 and pip
* JDK 17 or JDK 21
* Google Chrome web browser
* Git client (only for Bitbucket DC)

Please make sure you have a version of Chrome browser that is compatible with [ChromeDriver](http://chromedriver.chromium.org/downloads) version set in app/$product.yml file (modules->selenium->chromedriver->version).

If a first part of ChromeDriver version does not match with a first part of your Chrome browser version, update Chrome browser or set compatible [ChromeDriver](http://chromedriver.chromium.org/downloads) version in .yml file.

### macOS setup
Make sure that you have:
* [Python](https://www.python.org/downloads/) (see [dependencies](#dependencies) section for supported versions)
* pip
* [JDK 17](https://www.oracle.com/java/technologies/downloads/#java17) installed
* XCode Command Line Tools
* Google Chrome web browser
```
python3 --version
pip --version
java -version
# command to check if XCode Command Line Tools installed
xcode-select --print-path
# or command to install if XCode Command Line Tools
xcode-select --install
```
For Bitbucket DC check that [Git](https://git-scm.com/downloads) is installed:
```
git --version
```

We recommend using [virtualenv](https://virtualenv.pypa.io/en/latest/) for Taurus.

1. Install virtualenv with pip:
```
pip install virtualenv
```
2. Create new virtual env with python3:
```
virtualenv venv -p full_path_to_python # e.g. use `which python3.11` to find the path
```
3. Activate virtual env:
```
source venv/bin/activate
```
4. Install dependencies:
```
pip install -r requirements.txt
```
5. Optional: to use locust as main load-executor while running tests uninstall 'trio' and 'trio-websocket because they conflict with gevent monkey-patching used by bzt's Locust wrapper:
```
pip uninstall -y trio trio-websocket
```

### Linux setup
Make sure that you have:
* [Python](https://www.python.org/downloads/) (see [dependencies](#dependencies) section for supported versions)
* pip
* [JDK 17](https://www.oracle.com/java/technologies/downloads/#java17) installed
* Python developer package (e.g. `python3.11-dev` package for Python3.11)
* Google Chrome web browser
```
python3 --version
pip --version
java -version
```
For Bitbucket DC check that [Git](https://git-scm.com/downloads) is installed:
```
git --version
```
We recommend using [virtualenv](https://virtualenv.pypa.io/en/latest/) for Taurus. See example setup below.

## Example setup for clean Ubuntu 22.04
JDK setup (if missing):
```
sudo apt-get update
sudo apt-get install -y openjdk-17-jre-headless
```
Chrome setup (if missing):
```
sudo apt-get update
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo apt-get install -y ./google-chrome-stable_current_amd64.deb
```
Python and virtualenv setup:
```
sudo apt-get update
sudo apt-get -y install python3.11-dev python3-pip virtualenv
sudo update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1
virtualenv venv -p /usr/bin/python
source venv/bin/activate
pip install -r requirements.txt
```

### Windows setup
#### Installing Taurus manually
Make sure you have [Python](https://www.python.org/downloads/) (see [dependencies](#dependencies) section for supported versions), pip, and [JDK 17](https://www.oracle.com/java/technologies/downloads/#java17) installed:
```
python --version or python3 --version
pip --version
java -version
Microsoft Visual C++ 14
Windows 10 SDK
```
For Bitbucket Server check that [Git](https://git-scm.com/downloads) is installed:
```
git --version
```

Make sure you have Visual Studio build tool v14.22 installed. 
Otherwise, download it from [Microsoft Visual C++ Build Tools:](https://visualstudio.microsoft.com/downloads) and do the following:
1. Select **Tools for Visual Studio 2019**.
2. Download and run **Build Tools for Visual Studio 2019**.
3. Select the **C++ build tools** check box.
4. Select the **MSVC v142 - VS 2019 C++ x64/x86 build tools (v14.22)** check box (clear all the others).
5. Click **Install**.

Setup [Windows 10 SDK](https://developer.microsoft.com/en-us/windows/downloads/windows-10-sdk/)

We recommend using [virtualenv](https://virtualenv.pypa.io/en/latest/) for Taurus.
1. Install virtualenv with pip:
```
pip install virtualenv
```
2. Create new virtual env with python3:
```
virtualenv venv -p full_path_to_python # e.g. use `where python` to find the path to correct python
```
3. Activate virtual env:
```
venv\Scripts\activate
```
4. Install dependencies:
```
pip install -r requirements.txt
```

## Upgrading the toolkit
Get latest codebase from master branch:
```
git pull
```
Activate virtual env for the toolkit and install latest versions of libraries:
```
pip install -r requirements.txt
```

## Additional info
Official Taurus installation instructions are located [here](https://gettaurus.org/docs/Installation/).

## Analytics
The Data Center App Performance Toolkit includes some simple usage analytics.  
We collect this data to better understand how the community is using the Performance Toolkit, and to help us plan our roadmap.
When a performance tests is completed we send one HTTP POST request with analytics.

The request include the following data, and will in no way contain PII (Personally Identifiable Information).
- application under test (Jira/Confluence/Bitbucket)
- timestamp of performance toolkit run
- performance toolkit version
- operating system
- `concurrency` and `test_duration` from `$product.yml` file
- actual run duration
- executed action names and success rates
- unique user identifier (non PII)

To help us continue improving the Toolkit, we’d love you to keep these analytics enabled in testing, staging, and production. If you don’t want to send us analytics, you can turn off the `allow_analytics` toggle in `$product.yml` file.

## Running Taurus
Navigate to [docs](docs) folder and follow instructions.
