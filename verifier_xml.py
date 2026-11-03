from pathlib import Path
from lxml import etree

XML_FOLDER = Path(r"C:\Users\Aya\Documents\Data_arch\data")

xml_files = list(XML_FOLDER.rglob("*.xml"))

valid = 0
invalid = 0

parser = etree.XMLParser(
    resolve_entities=False,
    no_network=True
)

for file in xml_files:
    try:
        etree.parse(str(file), parser)
        valid += 1
    except etree.XMLSyntaxError:
        invalid += 1

print("Total XML files:", len(xml_files))
print("Valid XML files:", valid)
print("Invalid XML files:", invalid)