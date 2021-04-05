import click
import json
import pprint
import datetime
from datetime import timezone
import re
import configparser
import sys

from jira import JIRA, client as jira_manager
import requests

# get custom configuration
config = configparser.ConfigParser()
config.read('config.ini')


PROVIDERS = 'all-providers.json'
RESOURCES = 'all-resources.json'

all_providers = json.load(open(PROVIDERS, 'r'))['results']
all_resources = json.load(open(RESOURCES, 'r'))['results']

# convenience map of provider codes to names
provider_names = {provider['id']: provider['name'] for provider in all_providers}


@click.group()
def main():
    """
    Simple CLI for querying EOSC provider database
    """
    pass


def filter_providers(provider_name=None):
    if provider_name:
        return [provider for provider in all_providers if
                provider_name in provider['abbreviation'] or provider_name in provider['name']]
    return [provider for provider in all_providers]


def filter_resources(resource_name=None, provider_name=None):
    if not resource_name and not provider_name:
        return [resource for resource in all_resources]

    result = []
    for resource in all_resources:
        if len(resource['resourceProviders']) < 1:
            print(f'ERROR DETECTED: {resource["name"]} does not have any connected providers')
            continue
        resource_provider_code = resource['resourceProviders'][0]
        resource_provider_name = provider_names[resource_provider_code]
        if resource_name and resource_name not in resource['name']:
            continue
        if provider_name and provider_name not in resource_provider_name:
            continue
        result.append(resource)
    return result


@main.command()
@click.option('--provider_name', '-n', required=False)
def list_providers(provider_name=None):
    click.echo([provider['name'] for provider in filter_providers(provider_name)])


@main.command()
@click.option('--resource_name', '-n', required=False)
@click.option('--provider_name', '-p', required=False)
def list_resources(resource_name, provider_name):
    click.echo([resource['name'] for resource in filter_resources(resource_name, provider_name)])


@main.command()
@click.option('--provider_name', '-n', required=False)
@click.option('--verbose', '-v', is_flag=True, default=False)
def show_provider(provider_name, verbose):
    # find a provider matching name
    found_providers = [provider for provider in filter_providers(provider_name)]
    if verbose:
        for p in found_providers:
            click.echo(pprint.pformat(p))
            click.echo("========= RESOURCES =========")
            click.echo(pprint.pformat(
                [resource['name'] for resource in filter_resources(resource_name=None, provider_name=p['name'])]))
    else:
        click.echo(pprint.pformat(found_providers))


@main.command()
@click.option('--resource_name', '-n', required=False)
@click.option('--provider_name', '-p', required=False)
def show_resource(resource_name, provider_name):
    # find a resource matching name
    click.echo(pprint.pformat([resource for resource in filter_resources(resource_name, provider_name)]))


def jira_client(url, username, password):
    return JIRA(
        server=url,
        basic_auth=(username, password),
        validate=False,
    )


def jira_result_line(check, result, comment):
    results = {
        'OK': '(/)',
        'BAD': '(x)',
        'WARNING': '(!)'
    }
    return results[result] + " " + check + ". " + comment + '\n'


def get_resource_validations(resource):
    result = ""
    if not resource['mainContact']:
        result += jira_result_line('Provider contacts', 'BAD',
                                   f'Provider does not have main contacts defined.')
    # TRL
    if resource['trl'] not in ['trl-7', 'trl-8', 'trl-9']:
        result += jira_result_line('TRL', 'BAD',
                                   f'TRL level is beyond allowed for EOSC: {resource["trl"]}.')
    else:
        result += jira_result_line('TRL', 'OK',
                                   f'TRL level is acceptable by EOSC: {resource["trl"]}.')

    # Web page
    if not resource['webpage']:
        result += jira_result_line('Web page', 'BAD',
                                   f'Resource is missing a web page')
    else:
        url = resource['webpage']
        # download the first page
        try:
            page: requests.Response = requests.get(url)
        except Exception as e:
            result += jira_result_line('Web page', 'BAD',
                                       f'Error loading web page {url}: {e}')
        else:
            if page.status_code >= 400:
                result += jira_result_line('Web page', 'BAD',
                                           f'Could not load web page {url}.')
            # check if EOSC is mentioned, very fragile
            if 'eosc' not in page.text.lower() and 'researcher' not in page.text.lower() and 'researchers' not in page.text.lower():
                result += jira_result_line('Web page', 'WARNING',
                                           f'EOSC or researchers are not mentioned on the landing page of a resource {url}.')
            else:
                result += jira_result_line('Web page', 'OK',
                                           f'EOSC or researchers are mentioned on the landing page of a resource {url}.')

    return result


def get_provider_validations(provider):
    result = ""
    # check if contact details are present
    if not provider['mainContact']:
        result += jira_result_line('Provider contacts', 'BAD',
                                   f'Provider does not have main contacts defined.')

    # Check if provider claims to be legal entity
    if provider['legalEntity']:
        result += jira_result_line('Provider legal status', 'OK',
                                   f'Provider claims to be a legal entity of type {provider["legalStatus"][22:]}.')
    else:
        # check if 'hostingLegalEntity' is set
        if provider['hostingLegalEntity']:
            # check if provider exists in the record
            found_providers = [provider for provider in filter_providers(provider['hostingLegalEntity'])]
            if len(found_providers) == 1:
                jira_result_line('Provider legal status', 'OK',
                                 f'Provider is not a legal body but claims to be represented by {provider["hostingLegalEntity"]}.')
            elif len(found_providers) > 1:
                jira_result_line('Provider legal status', 'WARNING',
                                 f'Provider is not a legal body but claims to be represented by {provider["hostingLegalEntity"]}. We have found several entities that match the name.')
        else:

            result += jira_result_line('Provider legal status', 'BAD',
                                       f'Provider is not a legal body and does not have linked hosting legal entities.')

    return result
    # Provider needs to EITHER be a legal entity or if not (e.g. a project) should be linked to a legal entity registered int he portal. We recommend registering via a legal entity is possible as this increases the sustainability of the entry versus project contacts which may disappear.
    # At least TRL7
    # Be available to European users and basic info in English so we can validate it.


def create_provider_validation_issue(client, provider, dry_run):
    click.echo('\tCreating a new task for provider validation.')
    # main contact might be empty
    contact_name = 'Missing'
    contact_email = 'Missing'
    if provider['mainContact']:
        contact_name = provider['mainContact']['firstName'] + '  ' + provider['mainContact']['lastName']
        contact_email = provider['mainContact']['email']
    fields = {
        "issuetype": 'Provider',
        "project": 'EOSCOB',
        "summary": provider["abbreviation"],
        "customfield_12006": contact_name,
        "customfield_12008": contact_email,
        "description": "h3. Results of automatic validation:\n" + get_provider_validations(provider),  # TODO
        "customfield_12009": 'https://providers.eosc-portal.eu/provider/info/' + provider['id']
    }

    if dry_run:
        print('Would have created issue with the following data:')
        pprint.pprint(fields)
        return None
    else:
        issue: jira_manager.Issue = client.create_issue(fields=fields)
        click.echo(f'Created issue {issue.key}, assigned to {issue.fields.assignee}.')
        click.echo('Moving state to Submitted application.')
        client.transition_issue(issue, 'Submitted application')
        click.echo('Moving state to Application requires review.')
        client.transition_issue(issue, 'Application requires review')
        return issue


def create_resource_validation_issue(client, parent_issue, resource, dry_run):
    click.echo('\tCreating a new task for resource validation.')
    contact_name = 'Missing'
    contact_email = 'Missing'
    if resource['mainContact']:
        contact_name = resource['mainContact']['firstName'] + '  ' + resource['mainContact']['lastName']
        contact_email = resource['mainContact']['email']

    fields = {
        "issuetype": 'Resource ',
        "project": 'EOSCOB',
        "summary": resource["name"],
        "parent": {'key': parent_issue.key} if parent_issue else None,
        "customfield_12010": resource["name"],  # TODO: why to duplicate summary?
        "customfield_12011": {'value': 'Service'},  # TODO: how to understand this?
        "customfield_12012": contact_name,  #
        "customfield_12014": contact_email,
        "description": "h3. Results of automatic validation\n" + get_resource_validations(resource),  # TODO
        "customfield_12015": f'https://providers.eosc-portal.eu/provider/{resource["resourceOrganisation"]}/resource/update/{resource["id"]}'
                             ""
    }

    if dry_run:
        print('\tWould have created issue with the following data:')
        pprint.pprint(fields)
        return None
    else:
        issue: jira_manager.Issue = client.create_issue(fields=fields)
        click.echo(f'Created issue {issue.key}, assigned to {issue.fields.assignee}.')
        click.echo('Moving state to Submitted application.')
        client.transition_issue(issue, 'Submitted application')
        click.echo('Moving state to Application requires review.')
        client.transition_issue(issue, 'Application requires review')
        return issue


@main.command()
@click.option('--provider_name', '-p', required=False)
@click.option('--dry_run/--no-dry_run', default=True)
def check_eoscob_tasks(provider_name, dry_run):
    # find a resource matching name
    client = jira_client(config['jira']['url'], config['jira']['username'], config['jira']['password'])
    # check if a validation ticket exists for each provider
    found_providers = [provider for provider in filter_providers(provider_name)]
    ticket_counter = 0  # total counter of created tickets
    for provider in found_providers:
        click.echo(f'Checking auditing issues for provider {provider["name"]}')
        # need to trigger validation?
        need_to_validate_provider = True

        provider_issues: jira_manager.ResultList = client.search_issues(
            f'project = EOSCOB AND issuetype = Provider AND summary ~ "{provider["abbreviation"]}" order by created DESC')
        last_provider_issue = None
        if provider_issues.total == 0:
            click.echo('\tNo auditing issues found.')
        else:
            for provider_issue in provider_issues:
                if last_provider_issue is None:
                    last_provider_issue = provider_issue  # save for later, we order by creation time
                click.echo(
                    f'\tFound issue {provider_issue.key} with status {provider_issue.fields.status} assigned to {provider_issue.fields.assignee}.')
                if str(provider_issue.fields.status) in ['Record approved', 'Rejected', 'Record suspended']:
                    dt = datetime.datetime.strptime(provider_issue.fields.resolutiondate, '%Y-%m-%dT%H:%M:%S.%f%z')
                    click.echo(
                        f'\tValidation has been performed {(datetime.datetime.now(timezone.utc) - dt).days} days ago, skipping provider validation.')
                else:
                    click.echo(f'\tValidation is on-going, skipping new issue creation.')

                need_to_validate_provider = False

        # create a new task for provider validation
        if need_to_validate_provider:
            last_provider_issue = create_provider_validation_issue(client, provider, dry_run)
            ticket_counter += 1

        # now create a sub-task for each of the resources
        for resource in filter_resources(resource_name=None, provider_name=provider['name']):
            need_to_validate_resource = True
            click.echo(f'Checking auditing issues for resource {resource["name"]} by {provider["abbreviation"]}.')
            cleaned_resource_name = re.sub(r"[\t]*", "", resource[
                "name"])  # TODO: FANTEN	 (Finding Anisotropy TENsor) has TABS in the name!
            resource_issues: jira_manager.ResultList = client.search_issues(
                f'project = EOSCOB AND issuetype = "Resource " AND summary ~ \"{cleaned_resource_name}\" order by created DESC')
            if resource_issues.total == 0:
                click.echo('\tNo auditing issues for resource found.')
            else:
                for resource_issue in resource_issues:
                    click.echo(
                        f'\tFound issue {resource_issue.key} with status {resource_issue.fields.status} assigned to {resource_issue.fields.assignee}.')
                    if str(provider_issue.fields.status) in ['Record approved', 'Rejected', 'Record suspended']:
                        click.echo(
                            f'\tValidation has been performed {(datetime.datetime.now(timezone.utc) - dt).days} days ago, skipping resource.')
                    else:
                        click.echo(f'\tValidation is on-going, skipping new issue creation.')

                    need_to_validate_resource = False

            if need_to_validate_resource:
                create_resource_validation_issue(client, last_provider_issue, resource, dry_run)
                ticket_counter += 1

    print(
        f'\nWould have created {ticket_counter} new issues. With average 5 minutes per ticket we have just saved {ticket_counter * 5} minutes of human life.')


def download_file(url, file_name):
    # inspired by https://stackoverflow.com/a/15645088
    with open(file_name, "wb") as f:
        print("Downloading %s" % file_name)
        response = requests.get(url, stream=True)
        total_length = response.headers.get('content-length')

        if total_length is None:  # no content length header
            f.write(response.content)
        else:
            dl = 0
            total_length = int(total_length)
            for data in response.iter_content(chunk_size=4096):
                dl += len(data)
                f.write(data)
                done = int(50 * dl / total_length)
                sys.stdout.write("\r[%s%s]" % ('=' * done, ' ' * (50 - done)))
                sys.stdout.flush()

@main.command()
def refresh_cache():
    # inspired by https://stackoverflow.com/a/15645088
    providers = 'https://providers.eosc-portal.eu/api/provider/all/?from=0&quantity=10000'
    resources = 'https://providers.eosc-portal.eu/api/service/all/?from=0&quantity=10000'
    download_file(providers, 'all-providers.json')
    download_file(resources, 'all-resources.json')


if __name__ == "__main__":
    main()
