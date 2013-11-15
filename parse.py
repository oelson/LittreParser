#-*- coding: utf-8 -*-

__all__ = ["parser", "entree"]

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
    
    def get_entree(self, name):
        """
        Récupère un noeud Element correspondant au mot recherché.
        Retourne une instance de la classe "entree".
        """
        # récupère le parseur adéquat
        name = name.upper()
        letter = name[0]
        p = self.get_parser(letter)
        node = p.find("./entree[@terme='{}']".format(name))
        if node is None:
            raise EntryNotFound("the entry \"{}\" does not exist".format(name))
        return entree(name, node)

class entree:
    """
    Une entrée du dictionnaire générée par le parseur.
    Une entrée correspond à une définition.
    """

    def __init__(self, mot, entree):
        self.mot = mot
        self.entree = entree

    def format(self):
        """
        Retourne la description de l'objet sus la forme d'un dictionnaire.
        """
        return _xml2dict(self.entree)

    def __repr__(self):
        return self.__str__()
    
    def __str__(self):
        return str(self.format())
