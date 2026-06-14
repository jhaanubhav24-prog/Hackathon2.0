"""
AST NODES
---------
Har JS construct (variable declaration, if statement, function call, etc.)
ke liye ek "Node" class. Parser yeh nodes banayega, Interpreter inhe traverse karega.

Hum simplicity ke liye generic Node class use kar rahe hain with a 'type' field
aur extra attributes set via kwargs. Yeh banane se naye node types add karna
asaan ho jaata hai bina baar baar naya class likhe.
"""


class Node:
    def __init__(self, type_, **kwargs):
        self.type = type_
        for k, v in kwargs.items():
            setattr(self, k, v)

    def __repr__(self):
        attrs = {k: v for k, v in self.__dict__.items() if k != "type"}
        return f"{self.type}({attrs})"
