#!/usr/bin/env python3
""" panzer: pandoc with styles

for more info: <https://github.com/msprev/panzer>

Author    : Mark Sprevak <mark.sprevak@ed.ac.uk>
Copyright : Copyright 2014, Mark Sprevak
License   : BSD3
"""

import argparse
import json
import logging
import logging.config
import os
import pandocfilters
import shlex
import subprocess
import sys
import tempfile
from .version import VERSION
from .util import *
__version__ = VERSION

REQUIRE_PANDOC_ATLEAST = "1.12.1"
DEFAULT_SUPPORT_DIR = os.path.join(os.path.expanduser('~'), '.panzer')
ENCODING = 'utf8'
T = 't'
C = 'c'
ADDITIVE_FIELDS = ['preflight',
                   'filter',
                   'postprocess',
                   'postflight',
                   'cleanup']


# Filters and pre/post-flight scripts

def run_scripts(kind, run_lists, json_message, force_run=False):
    """ execute commands of kind listed in run_lists """
    # - if no run list to run, then return
    if kind not in run_lists or not run_lists[kind]:
        return
    log('INFO', 'panzer', '-- %s --' % kind)
    for command in run_lists[kind]:
        filename = os.path.basename(command[0])
        fullpath = ' '.join(command).replace(os.path.expanduser('~'), '~')
        log('INFO', 'panzer', 'run "%s"' % fullpath)
        stderr = out_pipe = str()
        try:
            p = subprocess.Popen(command,
                                 stdin=subprocess.PIPE,
                                 stderr=subprocess.PIPE)
            # send panzer's json message to scripts via stdin
            in_pipe = json_message
            in_pipe_bytes = in_pipe.encode(ENCODING)
            out_pipe_bytes, stderr_bytes = p.communicate(input=in_pipe_bytes)
            if out_pipe_bytes:
                out_pipe = out_pipe_bytes.decode(ENCODING)
            if stderr_bytes:
                stderr = stderr_bytes.decode(ENCODING)
        except OSError as error:
            log('ERROR', filename, error)
            continue
        except Exception as error:
            # if force_run: always run next script
            if force_run:
                log('ERROR', filename, error)
                continue
            else:
                raise
        finally:
            log_stderr(stderr, filename)

def build_run_lists(metadata, run_lists, options):
    """ return run lists updated with metadata """
    for field in ADDITIVE_FIELDS:
        run_list = run_lists[field]
        # - if 'filter', add filter list specified on command line
        if field == 'filter' and options['pandoc']['filter']:
            run_list = [list(f) for f in options['pandoc']['filter']]
        #  - add commands specified in metadata
        if field in metadata:
            run_list.extend(build_run_list(metadata, field, options))
        # pdf output: skip postprocess
        if options['pandoc']['pdf_output'] \
           and field == 'postprocess' \
           and run_list:
            log('INFO', 'panzer', 'postprocess skipped --- since output is PDF')
            run_lists[field] = []
            continue
        # - filter be passed writer as 1st argument
        if field == 'filter':
            for command in run_list:
                command.insert(1, options['pandoc']['write'])
        run_lists[field] = run_list
        for (i, command) in enumerate(run_list):
            log('INFO',
                'panzer',
                '%s %d "%s"' % (field, i+1, " ".join(command)))
    return run_lists

def build_run_list(metadata, field, options):
    """ return run list for field of metadata """
    run_list = []
    try:
        metadata_list = get_content(metadata, field, 'MetaList')
    except (PanzerTypeError, PanzerKeyError) as error:
        log('WARNING', 'panzer', error)
        return run_list
    for item in metadata_list:
        check_c_and_t_exist(item)
        item_content = item[C]
        # command name
        command_raw = get_content(item_content, 'run', 'MetaInlines')
        command_str = pandocfilters.stringify(command_raw)
        command = [resolve_path(command_str, field, options)]
        # arguments
        arguments = []
        if 'args' in item_content:
            if get_type(item_content, 'args') == 'MetaInlines':
                # arguments are raw string
                arguments_raw = get_content(item_content, 'args', 'MetaInlines')
                arguments_str = pandocfilters.stringify(arguments_raw)
                arguments = shlex.split(arguments_str)
            elif get_type(item_content, 'args') == 'MetaList':
                # arguments specified as MetaList
                arguments_list = get_content(item_content, 'args', 'MetaList')
                arguments = parse_args_metalist(arguments_list)
            command.extend(arguments)
        run_list.append(command)
    return run_list

def parse_args_metalist(arguments_list):
    """ return list of arguments from metadata list """
    arguments = []
    for item in arguments_list:
        if item[T] != 'MetaMap':
            log('ERROR',
                'panzer',
                '"args" list should have fields of type "MetaMap"')
            continue
        fields = item[C]
        if len(fields) != 1:
            log('ERROR',
                'panzer',
                '"args" list should have exactly one field per item')
            continue
        field_name = "".join(fields.keys())
        field_type = get_type(fields, field_name)
        field_value = get_content(fields, field_name, field_type)
        if field_type == 'MetaBool':
            arguments.append('--' + field_name)
        elif field_type == 'MetaInlines':
            value_str = pandocfilters.stringify(field_value)
            arguments.append('--%s="%s"' % (field_name, value_str))
        else:
            log('ERROR',
                'panzer',
                'arguments of type "%s" not' 'supported---"%s" ignored'
                % (field_type, field_name))
    return arguments

def resolve_path(filename, field, options):
    """ return path to filename of kind field """
    basename = os.path.splitext(filename)[0]
    paths = []
    paths.append(filename)
    paths.append(os.path.join('panzer',
                              field,
                              filename))
    paths.append(os.path.join('panzer',
                              field,
                              basename,
                              filename))
    paths.append(os.path.join(options['panzer']['support'],
                              field,
                              filename))
    paths.append(os.path.join(options['panzer']['support'],
                              field,
                              basename,
                              filename))
    for path in paths:
        if os.path.exists(path):
            return path
    return filename





def default_run_lists():
    """ return default run lists """
    run_lists = {
        'preflight'   : [],
        'filter'      : [],
        'postprocess' : [],
        'postflight'  : [],
        'cleanup'     : []
    }
    return run_lists


# Main function

def main():
    """ the main function """
    options = default_options()
    run_lists = default_run_lists()
    json_message = make_json_message(Document(), run_lists, options)
    try:
        check_pandoc_exists()
        options = parse_cli_options(options)
        start_logger(options)
        check_support_directory(options)
        ast = load(options)
        global_styledef = load_yaml_styledef(options)
        doc = Document()
        doc.populate(ast, global_styledef)
        doc.transform(options)
        run_lists = build_run_lists(doc.get_metadata(), run_lists, options)
        doc.purge_styles()
        json_message = make_json_message(doc, run_lists, options)
        doc.inject_panzer_reserved_field(json_message)
        run_scripts('preflight', run_lists, json_message)
        doc.pipe_through('filter', run_lists)
        doc.pandoc(options)
        doc.pipe_through('postprocess', run_lists)
        doc.write(options)
        run_scripts('postflight', run_lists, json_message)
    except PanzerSetupError as error:
        # - errors that occur before logging starts
        print(error, file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError:
        log('CRITICAL',
            'panzer',
            'cannot continue because of fatal error')
        sys.exit(1)
    except (KeyError,
            PanzerKeyError,
            PanzerBadASTError,
            PanzerTypeError,
            PanzerInternalError) as error:
        # - panzer exceptions not caught elsewhere, should have been
        log('CRITICAL', 'panzer', error)
        sys.exit(1)
    finally:
        run_scripts('cleanup', run_lists, json_message, force_run=True)
        # - if temp file created in setup, remove it
        if options['panzer']['stdin_temp_file']:
            os.remove(options['panzer']['stdin_temp_file'])
            log('DEBUG',
                'panzer',
                'deleted temp file: %s'
                % options['panzer']['stdin_temp_file'])
        log('DEBUG', 'panzer', '>>>>> panzer quits <<<<<')
    # - successful exit
    sys.exit(0)

if __name__ == '__main__':
    main()
