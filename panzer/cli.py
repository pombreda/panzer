def default_options():
    """ return default options """
    options = {
        'panzer': {
            'support'         : DEFAULT_SUPPORT_DIR,
            'debug'           : False,
            'verbose'         : 1,
            'stdin_temp_file' : ''
        },
        'pandoc': {
            'input'      : [],
            'output'     : '-',
            'pdf_output' : False,
            'read'       : '',
            'write'      : '',
            'template'   : '',
            'filter'     : [],
            'options'    : []
        }
    }
    return options

def parse_cli_options(options):
    """ parse command line options """
    panzer_description = '''
    Panzer-specific arguments are prefixed by triple dashes ('---').
    All other arguments are passed to pandoc.

    Default support directory: "%s"
    ''' % DEFAULT_SUPPORT_DIR
    panzer_epilog = '''
    Copyright (C) 2014 Mark Sprevak
    Web:  http://sites.google.com/site/msprevak
    This is free software; see the source for copying conditions. There is no
    warranty, not even for merchantability or fitness for a particular purpose.
    '''
    # Adapted from https://github.com/jgm/pandoc/blob/master/pandoc.hs#L841
    pandoc_writer_mapping = {
        ""          : "markdown",
        ".tex"      : "latex",
        ".latex"    : "latex",
        ".ltx"      : "latex",
        ".context"  : "context",
        ".ctx"      : "context",
        ".rtf"      : "rtf",
        ".rst"      : "rst",
        ".s5"       : "s5",
        ".native"   : "native",
        ".json"     : "json",
        ".txt"      : "markdown",
        ".text"     : "markdown",
        ".md"       : "markdown",
        ".markdown" : "markdown",
        ".textile"  : "textile",
        ".lhs"      : "markdown+lhs",
        ".texi"     : "texinfo",
        ".texinfo"  : "texinfo",
        ".db"       : "docbook",
        ".odt"      : "odt",
        ".docx"     : "docx",
        ".epub"     : "epub",
        ".org"      : "org",
        ".asciidoc" : "asciidoc",
        ".pdf"      : "latex",
        ".fb2"      : "fb2",
        ".opml"     : "opml",
        ".1"        : "man",
        ".2"        : "man",
        ".3"        : "man",
        ".4"        : "man",
        ".5"        : "man",
        ".6"        : "man",
        ".7"        : "man",
        ".8"        : "man",
        ".9"        : "man"
    }
    # 1. Parse options specific to panzer
    panzer_parser = argparse.ArgumentParser(description=panzer_description,
                                            epilog=panzer_epilog,
                                            formatter_class=argparse.RawTextHelpFormatter)
    panzer_parser.add_argument("---panzer-support",
                               help='location of directory of support files')
    panzer_parser.add_argument("---debug",
                               action="store_true",
                               help='write debug info to panzer.log')
    panzer_parser.add_argument("---verbose",
                               type=int,
                               help='verbosity of console messages\n'
                               ' 0: silent\n'
                               ' 1: only errors and warnings\n'
                               ' 2: full info (default)')
    panzer_parser.add_argument('---version',
                               action='version',
                               version=('%(prog)s ' + __version__))
    panzer_known_raw, unknown = panzer_parser.parse_known_args()
    panzer_known = vars(panzer_known_raw)
    # 2. Update options with panzer-specific values
    for field in panzer_known:
        value = panzer_known[field]
        if value:
            options['panzer'][field] = value
    # 3. Parse options specific to pandoc
    pandoc_parser = argparse.ArgumentParser(prog='pandoc')
    pandoc_parser.add_argument("--read",
                               "-r",
                               "--from",
                               "-f",
                               help='reader')
    pandoc_parser.add_argument("--write",
                               "-w",
                               "--to",
                               "-t",
                               help='writer')
    pandoc_parser.add_argument("--output",
                               "-o",
                               help='output')
    pandoc_parser.add_argument("--template",
                               help='template')
    pandoc_parser.add_argument("--filter",
                               "-F",
                               nargs=1,
                               action='append',
                               help='filter')
    pandoc_known_raw, unknown = pandoc_parser.parse_known_args(unknown)
    pandoc_known = vars(pandoc_known_raw)
    # 2. Update options with pandoc-specific values
    for field in pandoc_known:
        value = pandoc_known[field]
        if value:
            options['pandoc'][field] = value
    # 3. Check for pandoc output being pdf
    if os.path.splitext(options['pandoc']['output'])[1].lower() == '.pdf':
        options['pandoc']['pdf_output'] = True
    # 4. Detect pandoc's writer
    # - first case: writer explicitly specified by cli option
    if options['pandoc']['write']:
        pass
    # - second case: html default writer for stdout
    elif options['pandoc']['output'] == '-':
        options['pandoc']['write'] = 'html'
    # - third case: writer set via output filename extension
    else:
        ext = os.path.splitext(options['pandoc']['output'])[1].lower()
        implicit_writer = pandoc_writer_mapping.get(ext)
        if implicit_writer is not None:
            options['pandoc']['write'] = implicit_writer
        else:
            # - html is default writer for unrecognised extensions
            options['pandoc']['write'] = 'html'
    # 5. Input from stdin
    # - if one of the inputs is stdin then read from stdin now into
    # - temp file, then replace '-'s in input filelist with reference to file
    if '-' in unknown:
        # Read from stdin now into temp file in cwd
        stdin_bytes = sys.stdin.buffer.read()
        with tempfile.NamedTemporaryFile(prefix='__panzer-',
                                         suffix='__',
                                         dir=os.getcwd(),
                                         delete=False) as temp_file:
            temp_filename = os.path.join(os.getcwd(), temp_file.name)
            options['panzer']['stdin_temp_file'] = temp_filename
            temp_file.write(stdin_bytes)
            temp_file.flush()
        # Replace all reference to stdin in pandoc cli with temp file
        for index, value in enumerate(unknown):
            if value == '-':
                unknown[index] = options['panzer']['stdin_temp_file']
    # 6. Other input files
    # - detect input files by using `pandoc --dump-args`
    command = ['pandoc', '--dump-args'] + unknown
    stdout_bytes = subprocess.check_output(command)
    stdout = stdout_bytes.decode(ENCODING)
    stdout_list = stdout.splitlines()
    # - first line is output file, ignore it
    options['pandoc']['input'] = stdout_list[1:]
    # - remove input files from unknown
    unknown = [arg for arg in unknown
               if arg not in options['pandoc']['input']]
    # 7. Remaining options for pandoc
    options['pandoc']['options'] = unknown
    return options

