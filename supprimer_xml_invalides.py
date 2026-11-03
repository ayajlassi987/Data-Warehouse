
from pathlib import Path
from lxml import etree
import pandas as pd
import shutil

# 1. Dossier contenant les fichiers XML originaux
XML_FOLDER = Path(r"C:\Users\Aya\Documents\Data_arch\Data")

# 2. Dossier où déplacer les fichiers invalides
QUARANTINE_FOLDER = XML_FOLDER.parent / "xml_invalides"

# Créer le dossier de quarantaine
QUARANTINE_FOLDER.mkdir(parents=True, exist_ok=True)

# 3. Rapport des opérations
report = []

for xml_file in XML_FOLDER.rglob("*.xml"):

    # Éviter de parcourir le dossier de quarantaine
    if QUARANTINE_FOLDER in xml_file.parents:
        continue

    try:
        # Vérification stricte du XML
        etree.parse(
            str(xml_file),
            etree.XMLParser(
                resolve_entities=False,
                no_network=True
            )
        )

        report.append({
            "fichier": str(xml_file),
            "statut": "VALIDE",
            "erreur": ""
        })

    except (etree.XMLSyntaxError, OSError) as e:

        # Conserver la structure des sous-dossiers
        relative_path = xml_file.relative_to(XML_FOLDER)
        destination = QUARANTINE_FOLDER / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)

        try:
            # Déplacer le fichier invalide
            shutil.move(str(xml_file), str(destination))

            report.append({
                "fichier": str(xml_file),
                "statut": "DEPLACE_EN_QUARANTAINE",
                "erreur": str(e)
            })

        except OSError as move_error:
            report.append({
                "fichier": str(xml_file),
                "statut": "ECHEC_DU_DEPLACEMENT",
                "erreur": str(move_error)
            })

# 4. Enregistrer le rapport
report_path = XML_FOLDER.parent / "rapport_suppression_xml.csv"

pd.DataFrame(report).to_csv(
    report_path,
    index=False,
    encoding="utf-8-sig"
)

# 5. Afficher le bilan
df = pd.DataFrame(report)

print("\n--- BILAN ---")
print("Fichiers analysés :", len(df))
print("Fichiers valides :", (df["statut"] == "VALIDE").sum())
print(
    "Fichiers invalides déplacés :",
    (df["statut"] == "DEPLACE_EN_QUARANTAINE").sum()
)
print(
    "Échecs de déplacement :",
    (df["statut"] == "ECHEC_DU_DEPLACEMENT").sum()
)
print("Rapport :", report_path)
print("Fichiers invalides conservés dans :", QUARANTINE_FOLDER)
