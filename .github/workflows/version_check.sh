#!/bin/bash

VERSION_FILE_PATH="odev/_version.py"

function determine_version_file_line() {
    echo `cat $VERSION_FILE_PATH | grep -n '^__version__' | cut -d : -f 1`
}

function raise_file_version_wrong() {
    echo "::error file=$VERSION_FILE_PATH,line=$(determine_version_file_line),title=$1::$2. $ERROR_MESSAGE"
    exit 2
}

function exit_ok() {
    echo "::notice file=$VERSION_FILE_PATH,line=$(determine_version_file_line), title=$1::$1"
    exit 0
}

ERROR_MESSAGE="Please update incrementally the __version__ value on $VERSION_FILE_PATH"

GIT_DIFF=`git diff HEAD^1 HEAD $VERSION_FILE_PATH | grep __version__`

if [ -z "$GIT_DIFF" ]; then
    raise_file_version_wrong "Version Not Updated" "The odev version has not been updated"
fi

PREVIOUS_VERSION=`echo $GIT_DIFF | grep -Po '^-.*\+' | grep -Po '\d+(\.\d+)*'`
AFTER_VERSION=`echo $GIT_DIFF | grep -Po '\+.*' | grep -Po '\d+(\.\d+)*'`

IFS=. read prev_major prev_minor prev_patch <<< $PREVIOUS_VERSION
IFS=. read after_major after_minor after_patch <<< $AFTER_VERSION


echo "::notice::Comparing previous PR version: '$PREVIOUS_VERSION' and current PR version: '$AFTER_VERSION'"
if  [ $after_major -gt $prev_major ] ||
    [ $after_minor -gt $prev_minor ] ||
    [ $after_patch -gt $prev_patch ];
then
    # Check if the update is coherent, the step should be incremental.
    if [ $after_major -eq $(( $prev_major + 1 )) ] &&
       [ $after_minor -eq "0" ] &&
       [ $after_patch -eq "0" ] ;
    then
        exit_ok "Major Update"
    elif [ $after_major -eq $prev_major ] &&
         [ $after_minor -eq $(( $prev_minor + 1 )) ] &&
         [ $after_patch -eq "0" ] ;
    then
        exit_ok "Minor Update"
    elif [ $after_major -eq $prev_major ] &&
         [ $after_minor -eq $prev_minor ] &&
         [ $after_patch -eq $(( $prev_patch + 1 )) ] ;
    then
        exit_ok "Patch Update"
    else
        raise_file_version_wrong "Version Update Not Incremental" "The new version value does not follow the incremental pattern (e.g: 1.2.3 -> 1.2.4 or 1.3.0 or 2.0.0)"
    fi
else
    raise_file_version_wrong "Version Outdated" "The new version is lower than or equal to the previous version"
fi
