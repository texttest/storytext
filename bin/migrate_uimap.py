#!/usr/bin/env python

from ConfigParser import ConfigParser
from ordereddict import OrderedDict
import sys

def make_parser():
    parser = ConfigParser(dict_type=OrderedDict)
    parser.optionxform = str
    return parser

def transform(sectionName):
    sectionName = sectionName.replace(",Dialog=", ", Dialog=")
    if sectionName.startswith("View="):
        if sectionName.endswith("Viewer"):
            return "Type=Viewer, " + sectionName.split(", ")[0]
        else:
            parts = sectionName.split(",")
            parts.reverse()
            if len(parts) == 1:
                parts.insert(0, "Type=View")
            return ", ".join(parts)
    else:
        return sectionName

if __name__ == "__main__":
    fileName = sys.argv[1]

    parser = make_parser()
    parser.read([ fileName ])

    newParser = make_parser()

    for section in parser.sections():
        newSection = transform(section)
        newParser.add_section(newSection)
        for option, value in parser.items(section):
            newParser.set(newSection, option, value)

    newParser.write(open(fileName + ".tmp", "w"))
