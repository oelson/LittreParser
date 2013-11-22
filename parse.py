#-*- coding: utf-8 -*-

__all__ = ["parser", "entry"]

import xml.etree.ElementTree as ET

from unidecode import unidecode
from LittreParser.error import EntryNotFound 


def _xml2dict(root):
    """
    Convert an XML node to a dictionnary.
    Recursive.
    """
    out = []
    for child in root.iterfind("./*"):
        out.append({
            "tag": child.tag,
            "text": child.text,
            "attrib": child.attrib,
            "children": _xml2dict(child)
        })
    return out

def _gettext(elem):
    """
    Équivalent DOM de la propriété "innerText"
    """
    return "".join(elem.itertext())

class parser:
    """
    Un parseur du dictionnaire XMLittré.
    """
    
    # piscine à parseur pour les 26 lettres de l'alphabet
    _ET_parsers = {}

    def __init__(self, xml_directory):
        self._xml_directory = xml_directory
    
    def load_xml_file(self, letter):
        """
        Le dictionnaire est subdivisé en 26 fichiers xml, nommés d'après les
        lettres de l'alphabet.
        Instancie un noeud Element à partir du contenu du fichier correspondant
        à la lettre et le range dans un dictionnaire.
        """
        if not isinstance(letter, str) or not len(letter) == 1:
            raise ValueError("need a letter from the alphabet")
        xml_path = "{}/{}.xml".format(
            self._xml_directory,
            letter
        )
        with open(xml_path, 'r') as xml_file:
            xml_content = xml_file.read()
            self._ET_parsers[letter] = ET.fromstring(xml_content)
    
    def get_parser(self, letter):
        """
        Obtient (éventuellement en l'instanciant à la volée) le bon parseur en
        fonction d'une lettre de l'alphabet.
        """
        letter = unidecode(letter.lower())
        if letter not in self._ET_parsers:
            self.load_xml_file(letter)
        return self._ET_parsers[letter]
    
    def get_entry(self, name):
        """
        Récupère un noeud Element correspondant au mot recherché.
        Retourne une instance de la classe "entry".
        """
        # récupère le parseur adéquat
        name = name.upper()
        letter = name[0]
        p = self.get_parser(letter)
        node = p.find("./entree[@terme='{}']".format(name))
        if node is None:
            raise EntryNotFound("the entry \"{}\" does not exist".format(name))
        return entry(name, node)


class entry:
    """
    Une entrée du dictionnaire générée par le parseur.
    Une entrée correspond à une définition.
    """
    FORMAT_TYPE_PLAINTEXT = 0
    FORMAT_TYPE_HTML      = 1
    
    # Liste à puce
    _bullet = u"\u00A0\u2219\u00A0"

    # Format de l'entête
    entete_format = """terme: {}
prononciation: {}
nature: {}"""
    
    # Format d'une variante
    variante_format = _bullet + "variante #{}: {}"
    
    
    def __init__(self, mot, entry):
        self.mot = mot
        self.entry = entry

    def __dict__(self):
        """
        Retourne la description de l'objet sous la forme d'un dictionnaire.
        """
        return _xml2dict(self.entry)

    def format(self, format_type=FORMAT_TYPE_PLAINTEXT):
        """
        """
        if format_type == self.FORMAT_TYPE_PLAINTEXT:
            return self.format_plaintext()
        elif format_type == self.FORMAT_TYPE_HTML:
            return self.format_html()
        else:
            raise ValueError
    
    def format_plaintext(self):
        """
        Les noms de noeuds XML finissent par un '_'.
        """
        # Entête de la définition
        entete_ = self.entry.find("./entete")
        prononciation_ = entete_.find("./prononciation")
        nature_ = entete_.find("./nature")
        entete = self.entete_format.format(
            self.entry.attrib["terme"],
            prononciation_.text,
            nature_.text,
        )
        # Corps de la définition
        corps_ = self.entry.find("./corps")
        corps = ""
        f = True
        for v in corps_.iterfind("./variante"):
            # Ajoute un saut de ligne entre chaque variante
            if f:
                f = False
            else:
                corps += "\n"
            # Texte de la variante
            id = v.attrib.get("num") or ""
            corps += self.variante_format.format(
                id,
                # premier morceau de texte directement inclus dans le noeud
                next(v.itertext()).strip()
            )
            # Adjoint les éventuelles citations propres à une variante
            for c in v.iterfind("./cit"):
                pass
        # Concaténation des sous-parties0
        return "{}\n{}".format(
            entete,
            corps
        )
    
    def format_html(self):
        pass

    def __repr__(self):
        return self.__str__()
    
    def __str__(self):
        return str(self.format())
