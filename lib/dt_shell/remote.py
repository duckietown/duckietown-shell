import json
import os
import urllib2

import dateutil.parser


def get_duckietown_server_url():
    V = 'DTSERVER'
    DEFAULT = 'http://frankfurt.co-design.science:81'
    return os.environ.get(V, DEFAULT)


def get_dtserver_user_info(token):
    """ Returns a dictionary with information about the user """
    server = get_duckietown_server_url()
    url = server + '/info'
    headers = {'X-Messaging-Token': token}
    req = urllib2.Request(url, headers=headers)
    res = urllib2.urlopen(req)
    data = res.read()
    result = json.loads(data)
    return result


def dtserver_submit(token, queue, data):
    server = get_duckietown_server_url()
    url = server + '/submissions'
    headers = {'X-Messaging-Token': token}

    data = {'queue': queue, 'parameters': data}
    req_data = json.dumps(data)
    req = urllib2.Request(url, headers=headers, data=req_data)
    req.get_method = lambda: 'POST'
    res = urllib2.urlopen(req)
    data = res.read()
    result = json.loads(data)
    return result


def dtserver_retire(token, submission_id):
    server = get_duckietown_server_url()
    url = server + '/submissions'
    headers = {'X-Messaging-Token': token}

    data = {'submission_id': submission_id}
    req_data = json.dumps(data)
    req = urllib2.Request(url, headers=headers, data=req_data)
    req.get_method = lambda: 'DELETE'
    res = urllib2.urlopen(req)
    data = res.read()
    result = json.loads(data)
    return result


def dtserver_get_user_submissions(token):
    """ Returns a dictionary with information about the user """
    server = get_duckietown_server_url()
    url = server + '/submissions'
    headers = {'X-Messaging-Token': token}
    req = urllib2.Request(url, headers=headers)
    res = urllib2.urlopen(req)
    data = res.read()
    result = json.loads(data)
    assert result['ok'], result['msg']
    submissions = result['submissions']

    for v in submissions.values():
        for k in ['date_submitted', 'last_status_change']:
            v[k] = dateutil.parser.parse(v[k])
    return submissions


def dtserver_work_submission(token, submission_id=None):
    server = get_duckietown_server_url()
    url = server + '/take-submission'
    headers = {'X-Messaging-Token': token}
    data = {'submission_id': submission_id}
    req_data = json.dumps(data)
    req = urllib2.Request(url, headers=headers, data=req_data)
    req.get_method = lambda: 'GET'
    res = urllib2.urlopen(req)
    data = res.read()
    result = json.loads(data)
    assert result['ok'], result['msg']

    return result


def dtserver_report_job(token, job_id, result, stats):
    server = get_duckietown_server_url()
    url = server + '/take-submission'
    headers = {'X-Messaging-Token': token}
    data = {'job_id': job_id,
            'result': result,
            'stats': stats}
    req_data = json.dumps(data)
    req = urllib2.Request(url, headers=headers, data=req_data)
    req.get_method = lambda: 'POST'
    res = urllib2.urlopen(req)
    data = res.read()
    result = json.loads(data)
    assert result['ok'], result['msg']
    return result
