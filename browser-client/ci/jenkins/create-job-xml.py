#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Produce reviewed new-job XML privately; never creates or changes a job."""
import argparse
import json
import os
from pathlib import Path
import re
import stat
import xml.etree.ElementTree as ET


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--agent-label-file',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    path=args.agent_label_file
    info=path.stat()
    if path.resolve(strict=True)!=path.absolute() or not stat.S_ISREG(info.st_mode) \
            or info.st_uid not in (0,os.getuid()) or info.st_mode & 0o077:
        raise RuntimeError('agent-label-file-must-be-private-canonical-owned-file')
    label=path.read_text().strip()
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}',label):
        raise RuntimeError('agent-label-must-be-one-reviewed-exact-selector')
    source=Path(__file__).with_name('Jenkinsfile.template').read_text()
    source=source.replace('@PRIVATE_AGENT_LABEL@',json.dumps(label))
    project=ET.Element('flow-definition')
    ET.SubElement(project,'description').text='Isolated browser/native CI for the authorized fork at an exact reviewed source commit.'
    ET.SubElement(project,'keepDependencies').text='false'
    properties=ET.SubElement(project,'properties')
    # CLI parameter validation happens before the pipeline's properties() step.
    # Declare the same exact parameter and serialization policy on creation.
    parameters=ET.SubElement(properties,'hudson.model.ParametersDefinitionProperty')
    definitions=ET.SubElement(parameters,'parameterDefinitions')
    parameter=ET.SubElement(definitions,'hudson.model.StringParameterDefinition')
    ET.SubElement(parameter,'name').text='SOURCE_SHA'
    ET.SubElement(parameter,'description').text='Exact reviewed noah-be/overte topic commit'
    ET.SubElement(parameter,'defaultValue').text=''
    concurrent=ET.SubElement(properties,'org.jenkinsci.plugins.workflow.job.properties.DisableConcurrentBuildsJobProperty')
    ET.SubElement(concurrent,'abortPrevious').text='false'
    definition=ET.SubElement(project,'definition',{'class':'org.jenkinsci.plugins.workflow.cps.CpsFlowDefinition'})
    ET.SubElement(definition,'script').text=source
    ET.SubElement(definition,'sandbox').text='true'
    ET.SubElement(project,'triggers')
    ET.SubElement(project,'disabled').text='false'
    parent=args.output.parent
    if not parent.is_dir() or parent.stat().st_uid!=os.getuid() or parent.stat().st_mode & 0o077:
        raise RuntimeError('job-XML-output-parent-must-be-owned-mode0700-directory')
    descriptor=os.open(args.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(descriptor,'wb') as stream:
        stream.write(ET.tostring(project,encoding='utf-8',xml_declaration=True))
    print(json.dumps({'generated':True,'jenkinsMutation':'none','privateAgentSelector':'omitted'}))


if __name__=='__main__':main()
