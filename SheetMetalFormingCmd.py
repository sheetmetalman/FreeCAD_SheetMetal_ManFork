# -*- coding: utf-8 -*-
###################################################################################
#
#  SheetMetalFormingCmd.py
#
#  Copyright 2015 Shai Seger <shaise at gmail dot com>
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 2 of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public
#  License along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.
#
#
###################################################################################

import FreeCAD
import Part
import math
import os
import SheetMetalTools
from SheetMetalLogger import SMLogger

smEpsilon = SheetMetalTools.smEpsilon

def angleBetween(ve1, ve2):
    # Find angle between two vectors in degrees
    return math.degrees(ve1.getAngle(ve2))


def face_direction(face):
    yL = face.CenterOfMass
    uv = face.Surface.parameter(yL)
    nv = face.normalAt(uv[0], uv[1])
    direction = yL.sub(nv + yL)
    # print([direction, yL])
    return direction, yL


def transform_tool(tool, base_face, tool_face, point=FreeCAD.Vector(0, 0, 0), angle=0.0):
    # Find normal of faces & center to align faces
    direction1, yL1 = face_direction(base_face)
    direction2, yL2 = face_direction(tool_face)

    # Find angle between faces, axis of rotation & center of axis
    rot_angle = angleBetween(direction1, direction2)
    rot_axis = direction1.cross(direction2)
    if rot_axis.isEqual(FreeCAD.Vector(0.0, 0.0, 0.0), 0.001):
        rot_axis = FreeCAD.Vector(0, 1, 0).cross(direction2)
    rot_center = yL2
    # print([rot_center, rot_axis, rot_angle])
    if not rot_axis.isEqual(FreeCAD.Vector(0.0, 0.0, 0.0), 0.001):
        tool.rotate(rot_center, rot_axis, -rot_angle)
    tool.translate(-yL2 + yL1)
    # Part.show(tool, "tool")

    tool.rotate(yL1, direction1, angle)
    tool.translate(point)
    # Part.show(tool,"tool")
    return tool


def combine_solids(base, cut_tool, form_tool):
    form_tool = form_tool.cut(base)
    base = base.cut(cut_tool)
    return base.fuse(form_tool)


def makeforming(tool, base, base_face, thk, tool_faces=None, point=FreeCAD.Vector(0, 0, 0), angle=0.0):
    # create a shell from all faces but the selected ones
    cutSolid = tool.copy()
    cutSolid_tran = transform_tool(
        cutSolid, base_face, tool_faces[0], point, angle)
    base = base.copy()
    try:
        faces = []
        for face in tool.Faces:
            use_tool = True
            for selface in tool_faces:
                if face.isSame(selface):
                    use_tool = False
                    break
            if use_tool:
                faces.append(face)
        tool_shell = Part.makeShell(faces)

        offsetshell = tool_shell.makeOffsetShape(
            thk, 0.0, inter=False, self_inter=False, offsetMode=0, join=2, fill=True)
        offsetshell_tran = transform_tool(
            offsetshell, base_face, tool_faces[0], point, angle)
        base = combine_solids(base, cutSolid_tran, offsetshell_tran)
    except:
        FreeCAD.Console.PrintWarning("Forming faild. Trying alternate way.")
        offsetshell = tool.makeThickness(
            tool_faces, thk, 0.0001, False, False, 0, 0)
        offsetshell_tran = transform_tool(
            offsetshell, base_face, tool_faces[0], point, angle)
        base = combine_solids(base, cutSolid_tran, offsetshell_tran)

    # Part.show(base, "base")
    return base


class SMBendWall:
    def __init__(self, obj, selobj, selobj_items, seltool, seltool_items):
        '''"Add Forming Wall" '''

        _tip_ = FreeCAD.Qt.translate(
            "App::Property", "Offset from Center of Face")
        obj.addProperty("App::PropertyVectorDistance",
                        "offset", "Parameters", _tip_)
        _tip_ = FreeCAD.Qt.translate(
            "App::Property", "Suppress Forming Feature")
        obj.addProperty("App::PropertyBool", "SuppressFeature",
                        "Parameters", _tip_).SuppressFeature = False
        _tip_ = FreeCAD.Qt.translate("App::Property", "Tool Position Angle")
        obj.addProperty("App::PropertyAngle", "angle",
                        "Parameters", _tip_).angle = 0.0
        _tip_ = FreeCAD.Qt.translate(
            "App::Property", "Thickness of Sheetmetal")
        obj.addProperty("App::PropertyDistance",
                        "thickness", "Parameters", _tip_)
        _tip_ = FreeCAD.Qt.translate("App::Property", "Base Object")
        obj.addProperty("App::PropertyLinkSub", "baseObject", "Parameters",
                        _tip_).baseObject = (selobj, selobj_items)
        _tip_ = FreeCAD.Qt.translate("App::Property", "Forming Tool Object")
        obj.addProperty("App::PropertyLinkSub", "toolObject", "Parameters",
                        _tip_).toolObject = (seltool, seltool_items)
        _tip_ = FreeCAD.Qt.translate(
            "App::Property",
            "Sketch containing circle's points to multiply and pattern the embossed feature",
        )
        obj.addProperty("App::PropertyLink", "Sketch", "Parameters1", _tip_)
        obj.Proxy = self

    def execute(self, fp):
        '''"Print a short message when doing a recomputation, this method is mandatory" '''

        base = fp.baseObject[0].Shape
        base_face = base.getElement(
            SheetMetalTools.getElementFromTNP(fp.baseObject[1][0]))
        thk = SheetMetalTools.smGetThickness(base, base_face)
        fp.thickness = thk
        tool = fp.toolObject[0].Shape
        tool_faces = [tool.getElement(SheetMetalTools.getElementFromTNP(
            fp.toolObject[1][i])) for i in range(len(fp.toolObject[1]))]

        offsetlist = []
        if fp.Sketch:
            sketch = fp.Sketch.Shape
            for e in sketch.Edges:
                # print(type(e.Curve))
                if isinstance(e.Curve, (Part.Circle, Part.ArcOfCircle)):
                    pt1 = base_face.CenterOfMass
                    pt2 = e.Curve.Center
                    offsetPoint = pt2 - pt1
                    # print(offsetPoint)
                    offsetlist.append(offsetPoint)
        else:
            offsetlist.append(fp.offset)

        if not (fp.SuppressFeature):
            for i in range(len(offsetlist)):
                a = makeforming(tool, base, base_face, thk,
                                tool_faces, offsetlist[i], fp.angle.Value)
                # Part.show(a)
                base = a
        else:
            a = base
        fp.Shape = a
        SheetMetalTools.smHideObjects(
            fp.baseObject[0], fp.toolObject[0], fp.Sketch)

##########################################################################################################
# Gui code
##########################################################################################################


if SheetMetalTools.isGuiLoaded():
    from FreeCAD import Gui
    from PySide import QtCore, QtGui

    icons_path = SheetMetalTools.icons_path

    # add translations path
    Gui.addLanguagePath(SheetMetalTools.language_path)
    Gui.updateLocale()

    class SMFormingVP:
        "A View provider that nests children objects under the created one"

        def __init__(self, obj):
            obj.Proxy = self
            self.Object = obj.Object

        def attach(self, obj):
            self.Object = obj.Object
            return

        def setupContextMenu(self, viewObject, menu):
            action = menu.addAction(FreeCAD.Qt.translate(
                "QObject", "Edit %1").replace("%1", viewObject.Object.Label))
            action.triggered.connect(
                lambda: self.startDefaultEditMode(viewObject))
            return False

        def startDefaultEditMode(self, viewObject):
            document = viewObject.Document.Document
            if not document.HasPendingTransaction:
                text = FreeCAD.Qt.translate("QObject", "Edit %1").replace(
                    "%1", viewObject.Object.Label)
                document.openTransaction(text)
            viewObject.Document.setEdit(viewObject.Object, 0)

        def updateData(self, fp, prop):
            return

        def getDisplayModes(self, obj):
            modes = []
            return modes

        def setDisplayMode(self, mode):
            return mode

        def onChanged(self, vp, prop):
            return

        def __getstate__(self):
            #        return {'ObjectName' : self.Object.Name}
            return None

        def __setstate__(self, state):
            self.loads(state)

        # dumps and loads replace __getstate__ and __setstate__ post v. 0.21.2
        def dumps(self):
            return None

        def loads(self, state):
            if state is not None:
                import FreeCAD
                doc = FreeCAD.ActiveDocument  # crap
                self.Object = doc.getObject(state['ObjectName'])

        def claimChildren(self):
            objs = []
            if hasattr(self.Object, "baseObject"):
                objs.append(self.Object.baseObject[0])
            if hasattr(self.Object, "toolObject"):
                objs.append(self.Object.toolObject[0])
            if hasattr(self.Object, "Sketch"):
                objs.append(self.Object.Sketch)
            return objs

        def getIcon(self):
            return os.path.join(icons_path, 'SheetMetal_Forming.svg')

        def setEdit(self, vobj, mode):
            taskd = SMFormingWallTaskPanel()
            taskd.obj = vobj.Object
            taskd.update()
            self.Object.ViewObject.Visibility = False
            self.Object.baseObject[0].ViewObject.Visibility = True
            self.Object.toolObject[0].ViewObject.Visibility = True
            Gui.Control.showDialog(taskd)
            return True

        def unsetEdit(self, vobj, mode):
            Gui.Control.closeDialog()
            self.Object.baseObject[0].ViewObject.Visibility = False
            self.Object.toolObject[0].ViewObject.Visibility = False
            self.Object.ViewObject.Visibility = True
            return False

    class SMFormingPDVP:
        "A View provider that nests children objects under the created one"

        def __init__(self, obj):
            obj.Proxy = self
            self.Object = obj.Object

        def attach(self, obj):
            self.Object = obj.Object
            return

        def updateData(self, fp, prop):
            return

        def getDisplayModes(self, obj):
            modes = []
            return modes

        def setDisplayMode(self, mode):
            return mode

        def onChanged(self, vp, prop):
            return

        def __getstate__(self):
            #        return {'ObjectName' : self.Object.Name}
            return None

        def __setstate__(self, state):
            self.loads(state)

        # dumps and loads replace __getstate__ and __setstate__ post v. 0.21.2
        def dumps(self):
            return None

        def loads(self, state):
            if state is not None:
                doc = FreeCAD.ActiveDocument
                self.Object = doc.getObject(state['ObjectName'])

        def claimChildren(self):
            objs = []
            if hasattr(self.Object, "toolObject"):
                objs.append(self.Object.toolObject[0])
            if hasattr(self.Object, "Sketch"):
                objs.append(self.Object.Sketch)
            return objs

        def getIcon(self):
            return os.path.join(icons_path, 'SheetMetal_Forming.svg')

        def setEdit(self, vobj, mode):
            taskd = SMFormingWallTaskPanel()
            taskd.obj = vobj.Object
            taskd.update()
            self.Object.ViewObject.Visibility = False
            self.Object.baseObject[0].ViewObject.Visibility = True
            self.Object.toolObject[0].ViewObject.Visibility = False
            Gui.Control.showDialog(taskd)
            return True

        def unsetEdit(self, vobj, mode):
            Gui.Control.closeDialog()
            self.Object.baseObject[0].ViewObject.Visibility = False
            self.Object.toolObject[0].ViewObject.Visibility = False
            self.Object.ViewObject.Visibility = True
            return False

    class SMFormingWallTaskPanel:
        '''A TaskPanel for the Sheetmetal'''

        def __init__(self):

            self.obj = None
            self.form = QtGui.QWidget()
            self.form.setObjectName("SMFormingWallTaskPanel")
            self.form.setWindowTitle("Binded faces/edges list")
            self.grid = QtGui.QGridLayout(self.form)
            self.grid.setObjectName("grid")
            self.title = QtGui.QLabel(self.form)
            self.grid.addWidget(self.title, 0, 0, 1, 2)
            self.title.setText("Select new face(s)/Edge(s) and press Update")

            # tree
            self.tree = QtGui.QTreeWidget(self.form)
            self.grid.addWidget(self.tree, 1, 0, 1, 2)
            self.tree.setColumnCount(2)
            self.tree.setHeaderLabels(["Name", "Subelement"])

            # buttons
            self.addButton = QtGui.QPushButton(self.form)
            self.addButton.setObjectName("addButton")
            self.addButton.setIcon(QtGui.QIcon(
                os.path.join(icons_path, 'SheetMetal_Update.svg')))
            self.grid.addWidget(self.addButton, 3, 0, 1, 2)

            QtCore.QObject.connect(self.addButton, QtCore.SIGNAL(
                "clicked()"), self.updateElement)
            self.update()

        def isAllowedAlterSelection(self):
            return True

        def isAllowedAlterView(self):
            return True

        def getStandardButtons(self):
            return QtGui.QDialogButtonBox.Ok

        def update(self):
            'fills the treewidget'
            self.tree.clear()
            if self.obj:
                f = self.obj.baseObject
                if isinstance(f[1], list):
                    for subf in f[1]:
                        # FreeCAD.Console.PrintLog("item: " + subf + "\n")
                        item = QtGui.QTreeWidgetItem(self.tree)
                        item.setText(0, f[0].Name)
                        item.setIcon(0, QtGui.QIcon(":/icons/Tree_Part.svg"))
                        item.setText(1, subf)
                else:
                    item = QtGui.QTreeWidgetItem(self.tree)
                    item.setText(0, f[0].Name)
                    item.setIcon(0, QtGui.QIcon(":/icons/Tree_Part.svg"))
                    item.setText(1, f[1][0])

                f = self.obj.toolObject
                if isinstance(f[1], list):
                    for subf in f[1]:
                        # FreeCAD.Console.PrintLog("item: " + subf + "\n")
                        item = QtGui.QTreeWidgetItem(self.tree)
                        item.setText(0, f[0].Name)
                        item.setIcon(0, QtGui.QIcon(":/icons/Tree_Part.svg"))
                        item.setText(1, subf)
                else:
                    item = QtGui.QTreeWidgetItem(self.tree)
                    item.setText(0, f[0].Name)
                    item.setIcon(0, QtGui.QIcon(":/icons/Tree_Part.svg"))
                    item.setText(1, f[1][0])
            self.retranslateUi(self.form)

        def updateElement(self):
            if self.obj:
                sel = Gui.Selection.getSelectionEx()[0]
                if sel.HasSubObjects:
                    obj = sel.Object
                    for elt in sel.SubElementNames:
                        if "Face" in elt:
                            face = self.obj.baseObject
                            found = False
                            if (face[0] == obj.Name):
                                if isinstance(face[1], tuple):
                                    for subf in face[1]:
                                        if subf == elt:
                                            found = True
                                else:
                                    if (face[1][0] == elt):
                                        found = True
                            if not found:
                                self.obj.baseObject = (
                                    sel.Object, sel.SubElementNames)

                sel = Gui.Selection.getSelectionEx()[1]
                if sel.HasSubObjects:
                    obj = sel.Object
                    for elt in sel.SubElementNames:
                        if "Face" in elt:
                            face = self.obj.toolObject
                            found = False
                            if (face[0] == obj.Name):
                                if isinstance(face[1], tuple):
                                    for subf in face[1]:
                                        if subf == elt:
                                            found = True
                                else:
                                    if (face[1][0] == elt):
                                        found = True
                            if not found:
                                self.obj.toolObject = (
                                    sel.Object, sel.SubElementNames)
                self.update()

        def accept(self):
            FreeCAD.ActiveDocument.recompute()
            Gui.ActiveDocument.resetEdit()
            # self.obj.ViewObject.Visibility=True
            return True

        def retranslateUi(self, TaskPanel):
            # TaskPanel.setWindowTitle(QtGui.QApplication.translate("draft", "Faces", None))
            self.addButton.setText(
                QtGui.QApplication.translate("draft", "Update", None))

    class AddFormingWallCommand():
        """Add Forming Wall command"""

        def GetResources(self):
            return {'Pixmap': os.path.join(icons_path, 'SheetMetal_Forming.svg'),  # the name of a svg file available in the resources
                    'MenuText': FreeCAD.Qt.translate('SheetMetal', 'Make Forming in Wall'),
                    'Accel': "M, F",
                    'ToolTip': FreeCAD.Qt.translate('SheetMetal', 'Make a forming using tool in metal sheet\n'
                                                    '1. Select a flat face on sheet metal and\n'
                                                    '2. Select face(s) on forming tool Shape to create Formed sheetmetal.\n'
                                                    '3. Use Suppress in Property editor to disable during unfolding\n'
                                                    '4. Use Property editor to modify other parameters')}

        def Activated(self):
            doc = FreeCAD.ActiveDocument
            view = Gui.ActiveDocument.ActiveView
            activeBody = None
            sel = Gui.Selection.getSelectionEx()
            selobj = Gui.Selection.getSelectionEx()[0].Object
            viewConf = SheetMetalTools.GetViewConfig(selobj)
            if hasattr(view, 'getActiveObject'):
                activeBody = view.getActiveObject('pdbody')
            if not SheetMetalTools.smIsOperationLegal(activeBody, selobj):
                return
            doc.openTransaction("WallForming")
            if activeBody is None or not SheetMetalTools.smIsPartDesign(selobj):
                a = doc.addObject("Part::FeaturePython", "WallForming")
                SMBendWall(a, selobj, sel[0].SubElementNames,
                           sel[1].Object, sel[1].SubElementNames)
                SMFormingVP(a.ViewObject)
            else:
                # FreeCAD.Console.PrintLog("found active body: " + activeBody.Name)
                a = doc.addObject("PartDesign::FeaturePython", "WallForming")
                SMBendWall(a, selobj, sel[0].SubElementNames,
                           sel[1].Object, sel[1].SubElementNames)
                SMFormingPDVP(a.ViewObject)
                activeBody.addObject(a)
            SheetMetalTools.SetViewConfig(a, viewConf)
            doc.recompute()
            doc.commitTransaction()
            return

        def IsActive(self):
            if len(Gui.Selection.getSelection()) < 2 or len(Gui.Selection.getSelectionEx()[0].SubElementNames) < 1:
                return False
            selobj = Gui.Selection.getSelection()[0]
            if str(type(selobj)) == "<type 'Sketcher.SketchObject'>":
                return False
            for selFace in Gui.Selection.getSelectionEx()[0].SubObjects:
                if type(selFace) != Part.Face:
                    return False
            return True

    Gui.addCommand("SheetMetal_Forming", AddFormingWallCommand())
