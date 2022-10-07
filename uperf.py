#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import subprocess
import shutil
import sys
from datetime import datetime
import logging
import json 
import numpy, math

logging.basicConfig(level=logging.WARNING)

WORKLOAD = "./uperf.xml"
UPERF_RESULT_FILE = "./uperf_stdout.txt"

def _json_payload(results, data, sample):
    processed = []
    prev_bytes = 0
    prev_ops = 0
    prev_timestamp = 0.0
    for result in results:
        norm_ops = int(result[2]) - prev_ops
        if norm_ops == 0:
            norm_ltcy = 0.0
        else:
            norm_ltcy = ((float(result[0]) - prev_timestamp) / (norm_ops)) * 1000
        datapoint = {
            "workload": "uperf",
            "iteration": sample,
#            "uperf_ts": datetime.fromtimestamp(int(result[0].split(".")[0]) / 1000),
            "bytes": int(result[1]),
            "norm_byte": int(result[1]) - prev_bytes,
            "ops": int(result[2]),
            "norm_ops": norm_ops,
            "norm_ltcy": norm_ltcy,
        }
        datapoint.update(data)
        processed.append(datapoint)
        prev_timestamp = float(result[0])
        prev_bytes = int(result[1])
        prev_ops = int(result[2])
    return processed

def convert_size(size_bytes):
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return "%s %s" % (s, size_name[i])

def _avg_out(doc):
    out = {}
    norm_byte_list = []
    norm_ltcy_list = []
    for d in doc:
      norm_byte_list.append(d['norm_byte'])
      norm_ltcy_list.append(d['norm_ltcy'])

    out = {
            "norm_ltcy_p95": numpy.percentile(norm_ltcy_list, 95),
            "norm_ltcy_p99": numpy.percentile(norm_ltcy_list, 99),
            "norm_ltcy_avg": numpy.average(norm_ltcy_list),
            "norm_byte_avg": convert_size(numpy.average(norm_byte_list)*8)
    }
    return out

def _run_uperf():
    # short to long cli option for uperf:
    # verbose, all stats, raw output in ms, throughput collection interval is 1 second
    cmd = "uperf -v -a -R -i 1 -m {} -P 30000".format(WORKLOAD)
    process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    return stdout.strip().decode("utf-8"), stderr.strip().decode("utf-8"), process.returncode

def _parse_stdout(stdout):
    # This will effectivly give us:
    # <profile name="{{test}}-{{proto}}-{{wsize}}-{{rsize}}-{{nthr}}">
    config = re.findall(r"running profile:(.*) \.\.\.", stdout)[0]
    test_type, protocol, wsize, rsize, nthr = config.split("-")
    # This will yeild us this structure :
    #     timestamp, number of bytes, number of operations
    # [('1559581000962.0330', '0', '0'), ('1559581001962.8459', '4697358336', '286704') ]
    results = re.findall(r"timestamp_ms:(.*) name:Txn2 nr_bytes:(.*) nr_ops:(.*)", stdout)
    # We assume message_size=write_message_size to prevent breaking dependant implementations
    return (
        results,
        {
            "test_type": test_type,
            "protocol": protocol,
            "message_size": int(wsize),
            "read_message_size": int(rsize),
            "num_threads": int(nthr),
            "duration": len(results),
            "tool": "uperf",
            "test_config": "uperf",
            "starttime": float(results[0][0]) / 1000,
            "endtime": float(results[-1][0]) / 1000,
        },
    )

def main():
    if not os.path.exists(WORKLOAD):
        logging.critical("Workload file not found")
        exit(1)
        
    logging.info("Calling Uperf run function..")
    if os.path.exists(UPERF_RESULT_FILE):
        with open(UPERF_RESULT_FILE, "r") as f:
            stdout = f.read()
    else:
        stdout, stderr, rc = _run_uperf()
        if rc == 1:
            logging.error("UPerf failed to execute, trying one more time..")
            stdout, stderr, rc = _run_uperf()
            logging.error("stdout: {a}".format(a=stdout))
            logging.error("stderr: {a}".format(a=stderr))
            if rc == 1:
                logging.error("UPerf failed to execute a second time, stopping...")
                logging.error("stdout: {a}".format(a=stdout))
                logging.error("stderr: {a}".format(a=stderr))
                exit(1)
    results, data = _parse_stdout(stdout)
    documents = _json_payload(results, data, 3)
#    print(json.dumps(documents, indent=4, sort_keys=True))
    summarize = _avg_out(documents)
    print(json.dumps(summarize, indent=4, sort_keys=True))

main()
