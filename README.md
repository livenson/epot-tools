# EPOT tools

## Local deployment

### Create virtualenv and install dependencies
```bash
python -m venv venv
. venv/bin/activate
pip install -r requirements.txt
```

### Setup your Jira access
```bash
cp config.ini.example config.ini
# edit config.ini and set username and password to the ones you use
```
 

### With virtualenv active:
```bash

python epot.py  # see list of supported commands

python epot.py show-resource --help  # example of getting help for a specific command

Examples:

python epot.py refresh-cache  # to get the latest list of providers and resources
python epot.py list-providers -n Tartu  # to get a list of providers with optional filter by name
python epot.py show-provider -n Tartu -v  # to see more detailed view of provider
python epot.py list-resources -n Rock  # to see more a list of resources
python epot.py show-resource -n 'UT Rocket' -p Tartu 
```

### Auditing assist tool

To simplify process of checking for existing auditing records, a command has been added that checks for open
issues and status of the records. Command also performs basic automatic validation. Two examples are below.
Note that by default it runs with 'dry-run', pass --no-dry_run and make sure that you have correct Jira
credentials configured to create actual tickets.

```bash
$ python epot.py check-eoscob-tasks --dry_run -p Tartu
Checking auditing issues for provider University of Tartu
	Found issue EOSCOB-198 with status New registration assigned to Owen Appleton.
	Validation is on-going, skipping new issue creation.
	Found issue EOSCOB-197 with status Application requires review assigned to Owen Appleton.
	Validation is on-going, skipping new issue creation.
	Found issue EOSCOB-196 with status Application requires review assigned to Owen Appleton.
	Validation is on-going, skipping new issue creation.
	Found issue EOSCOB-195 with status Application requires review assigned to Owen Appleton.
	Validation is on-going, skipping new issue creation.
ERROR DETECTED: Open Research Knowledge Graph (ORKG) does not have any connected providers
Checking auditing issues for resource UT Rocket by University of Tartu.
	Found issue EOSCOB-200 with status New registration assigned to Owen Appleton.
	Validation is on-going, skipping new issue creation.
	Found issue EOSCOB-199 with status New registration assigned to Owen Appleton.
	Validation is on-going, skipping new issue creation.

Would have created 0 new issues. With average 5 minutes per ticket we have just saved 0 minutes of human

$ python epot.py check-eoscob-tasks --dry_run -p RBI
Checking auditing issues for provider Ruder Boškovic Institute
	No auditing issues found.
	Creating a new task for provider validation.
Would have created issue with the following data:
{'customfield_12006': 'Missing',
 'customfield_12008': 'Missing',
 'customfield_12009': 'https://providers.eosc-portal.eu/provider/info/rbi-hr',
 'description': 'h3. Results of automatic validation:\n'
                '(x) Provider contacts. Provider does not have main contacts '
                'defined.\n'
                '(/) Provider legal status. Provider claims to be a legal '
                'entity of type other.\n',
 'issuetype': 'Provider',
 'project': 'EOSCOB',
 'summary': 'RBI'}
ERROR DETECTED: Open Research Knowledge Graph (ORKG) does not have any connected providers
Checking auditing issues for resource DARIAH Science Gateway by RBI.
	No auditing issues for resource found.
	Creating a new task for resource validation.
	Would have created issue with the following data:
{'customfield_12010': 'DARIAH Science Gateway',
 'customfield_12011': {'value': 'Service'},
 'customfield_12012': 'Missing',
 'customfield_12014': 'Missing',
 'customfield_12015': 'https://providers.eosc-portal.eu/provider/rbi-hr/resource/update/rbi-hr.dariah_science_gateway',
 'description': 'h3. Results of automatic validation\n'
                '(x) Provider contacts. Provider does not have main contacts '
                'defined.\n'
                '(/) TRL. TRL level is acceptable by EOSC: trl-8.\n'
                '(!) Web page. EOSC or researchers are not mentioned on the '
                'landing page of a resource https://www.irb.hr/eng.\n',
 'issuetype': 'Resource ',
 'parent': None,
 'project': 'EOSCOB',
 'summary': 'DARIAH Science Gateway'}

Would have created 2 new issues. With average 5 minutes per ticket we have just saved 10 minutes of human life.
```

