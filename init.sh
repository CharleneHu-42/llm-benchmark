#!/bin/bash

mkdir logs
env | grep https_proxy | awk -F '=' '{print $2}' | xargs -I{} pip install -r requirements.txt --proxy {}
