# -*- coding: utf-8 -*-
"""
/***************************************************************************
 SignalAnalysis
                                 A QGIS plugin
 Perform Analysis
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                              -------------------
        begin                : 2023-05-05
        git sha              : $Format:%H$
        copyright            : (C) 2023 by Muhammad Farhan
        email                : mher.farhan@gmail.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication, QThread, pyqtSignal, QVariant
from qgis.PyQt.QtGui import QIcon, QColor
from qgis.PyQt.QtWidgets import QAction

# Initialize Qt resources from file resources.py
from .resources import *
# Import the code for the dialog
from .signal_analysis_dialog import SignalAnalysisDialog
import os.path
from qgis.core import (
    QgsVectorLayer,
    QgsPointXY,
    QgsGeometry,
    QgsSpatialIndex,
    QgsFeatureRequest,
    QgsField,
    QgsFeature,
    QgsCoordinateReferenceSystem,
    QgsCategorizedSymbolRenderer,
    QgsSymbol,
    QgsRendererCategory,
    QgsProject

)

import random



class Worker(QThread):
    finished = pyqtSignal() 
    progress = pyqtSignal(int)
    logs = pyqtSignal(str)
    log_text = str()

    def __init__(self, dlg, iface):
        super(QThread, self).__init__()
        # initialize the stop variable
        self.stopworker = False
        self.dlg = dlg 
        self.iface = iface
    
    def signal_analysis(self):
        # substitute with your code.
        try:
            mapcanvas = self.iface.mapCanvas()
            layers = mapcanvas.layers()
            tower_selected = self.dlg.tower_attribute_value.checkedItems()
            tower_name = ''.join(l for l in tower_selected)
            # # create a temporary line layer to connect civics to tower
            fields = [QgsField('id', QVariant.Int),
             QgsField('civic', QVariant.Int), QgsField('tower', QVariant.Int), QgsField('azimuth', QVariant.Int)]
            # create the line layer

            line_layer = QgsVectorLayer('LineString', f'{tower_name}', 'memory')
            line_layer.setCrs(QgsCoordinateReferenceSystem('EPSG:26920'))  

            # add the fields to the layer
            line_layer.startEditing()
            line_layer.dataProvider().addAttributes(fields)
            line_layer.commitChanges()

            # Add the layer to the map
            QgsProject.instance().addMapLayer(line_layer)
            

            # get all inputs
            self.tower_layer = self.dlg.tower_layer.currentText()
            self.civic_layer = self.dlg.civic_layer.currentText()

            self.tower_layer_attr = self.dlg.tower_attribute.currentText()
            self.civic_layer_attr = self.dlg.civic_attribute.currentText()
            
            self.civic_attr_value = self.dlg.civic_attribute_value.checkedItems()
            self.tower_attr_value = self.dlg.tower_attribute_value.checkedItems()
            
            self.tower_selected = self.dlg.tower_layer_selected.isChecked()
            self.civic_selected = self.dlg.civic_layer_selected.isChecked()
            self.threashold_check = self.dlg.threshold_check.isChecked()

            self.threashold = self.dlg.threshold.value()

            self.azimuth = self.dlg.azimuth.checkedItems()

            
            # get layers object
            for layerdd in layers:
                if layerdd.name() == self.tower_layer:
                    self.tower_layer_ = layerdd
                if layerdd.name() == self.civic_layer:
                    self.civic_layer_ = layerdd
            
            # create Spatial Index     
            civic_spatial_index = QgsSpatialIndex(self.civic_layer_.getFeatures())

            self.tower_index = QgsSpatialIndex(self.tower_layer_.getFeatures())
            # algo
            line_layer.startEditing()
            total = self.tower_layer_.featureCount()
            for iter, tower in enumerate(self.get_features(self.tower_layer_, self.tower_selected)):
                if not self.filter_attrs(self.tower_layer_attr, self.tower_attr_value, tower):
                    continue
                tower_geom = tower.geometry()
                nearest_point_features = civic_spatial_index.nearestNeighbor(tower_geom, 200)
                for civic in self.civic_layer_.getFeatures(QgsFeatureRequest().setFilterFids(nearest_point_features)):
                    if not self.filter_attrs(self.civic_layer_attr, self.civic_attr_value, civic):
                        continue
                    print(1)
                    civic_geom = civic.geometry()
                    if not self.filter_threashold(civic):
                        continue
                    print(2)
                    if not self.check_if_current_tower_is_nearest(civic, tower):
                        continue
                    print(3)
                    if not self.verify_tower_name(civic, tower):
                        continue
                    print(4)
                    if not self.verify_azimuth(civic_geom, tower_geom, civic):
                        continue
                    print(5)
                    self.civic_layer_.select(civic.id())
                    # create a line feature and add it to the layer
                    id = line_layer.featureCount()
                    feature = QgsFeature()
                    feature.setGeometry(QgsGeometry.fromPolylineXY([civic_geom.asPoint(), tower_geom.asPoint()]))  # define the line geometry
                    feature.setAttributes([int(id)+1, civic.id(), tower.id(), self.civic_azimuth])
                    line_layer.addFeature(feature)
            
                self.progress.emit(int((iter+1)/total*100))

            line_layer.commitChanges()
            idx = line_layer.fields().indexOf('azimuth')
            unique_values = line_layer.uniqueValues(idx)
            color_map = {}
            for value in unique_values:
                color_code = self.generate_unique_color()
                color_map[value] = QColor(color_code)
            # Create a categorized symbol renderer
            renderer = 	QgsCategorizedSymbolRenderer('azimuth', [])
            # Set a color for each category
            for value, color in color_map.items():
                symbol = QgsSymbol.defaultSymbol(line_layer.geometryType())
                symbol.setColor(color)
                category = QgsRendererCategory(str(value), symbol, str(value))
                renderer.addCategory(category)

                # Set the renderer for the layer
                line_layer.setRenderer(renderer)

                # Refresh the layer to update the symbology
                line_layer.triggerRepaint()
            
        except Exception as e:
            self.finished.emit()
            print(e)
        finally:
            self.progress.emit(100)
            self.finished.emit()

    def verify_tower_name(self, civic, tower):
        tower_name = tower.attribute('site')
        final_name = str()
        for name in tower_name:
            if name.isdigit():
                continue
            final_name += name
        civic_tower = civic.attribute('Best Serve')
        if not civic.attribute('Best Serve'):
            return False
        splitted_ = str(civic_tower).split('_')
    
        final_name = str(final_name).replace(' ', '')
        splitted_ = str(splitted_[0]).replace(' ', '')

        
        if final_name in splitted_:
            return True
        return False
        

    def generate_unique_color(self):
        """
        Generates a unique RGB color code.
        """
        r = random.randint(0, 255)
        g = random.randint(0, 255)
        b = random.randint(0, 255)
        return f"#{r:02x}{g:02x}{b:02x}"


    def filter_threashold(self, civic):
        if self.threashold_check:
            return True
        civic_threshold = civic.attribute('Received P')
        if civic_threshold >= self.threashold:
            return True
        return False


    def check_if_current_tower_is_nearest(self, civic, tower):
        civic_geom = civic.geometry()
        current_distance = civic_geom.distance(tower.geometry())
        get_tower = self.get_neighbors(civic.geometry())
        for tower in get_tower:
            distance = tower.geometry().distance(civic_geom)
            if current_distance > distance:
                return False
        else:
            return True

    def verify_azimuth(self, civic, tower, civic_feature):

        if not civic_feature.attribute('Best Serve'):
            return False
        civic_azi = civic_feature.attribute('Best Serve')
        splitted_ = str(civic_azi).split('_')[-1]
        civic_azi = splitted_[1:]
        if str(civic_azi) in self.azimuth:
            self.civic_azimuth = civic_azi
            return True
        return False

    
    def get_neighbors(self, geom):
        nearest_ids = self.tower_index.nearestNeighbor(geom, 10)
        features = self.tower_layer_.getFeatures(QgsFeatureRequest().setFilterFids(nearest_ids))   
        return features                

            
    def get_features(self, layer, isSelected):
        return layer.selectedFeatures() if isSelected else layer.getFeatures()
            
    def filter_attrs(self, attr, attr_value, feature):

        try:
            check = attr[0] 
            check = attr_value[0]
        except:
            return True
        
        if str(feature.attribute(attr)) in attr_value:
                return True
        else:
            return False


class SignalAnalysis:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface
        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)
        # initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'SignalAnalysis_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&Signal Analysis')

        # Check if plugin was started the first time in current QGIS session
        # Must be set in initGui() to survive plugin reloads
        self.first_start = None

    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('SignalAnalysis', message)

    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None):
        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type add_to_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            # Adds plugin icon to Plugins toolbar
            self.iface.addToolBarIcon(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        icon_path = ':/plugins/signal_analysis/icon.png'
        self.add_action(
            icon_path,
            text=self.tr(u'Signal Analysis'),
            callback=self.run,
            parent=self.iface.mainWindow())

        # will be set False in run()
        self.first_start = True

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&Signal Analysis'),
                action)
            self.iface.removeToolBarIcon(action)


    def run(self):
        """Run method that performs all the real work"""

        # Create the dialog with elements (after translation) and keep reference
        # Only create GUI ONCE in callback, so that it will only load when the plugin is started
        self.dlg = SignalAnalysisDialog()

        mapcanvas = self.iface.mapCanvas()
        layers = mapcanvas.layers()

        self.dlg.civic_layer.clear()
        self.dlg.tower_layer.clear()
        self.dlg.azimuth.clear()
        for layerdd in layers:
            if isinstance(layerdd, QgsVectorLayer):
                self.dlg.tower_layer.addItems([layerdd.name()])
                self.dlg.civic_layer.addItems([layerdd.name()])
        # triggers
        self.azimuth_dropdown()
        self.dlg.civic_layer.currentTextChanged.connect(self.azimuth_dropdown)
        self.dlg.threshold_check.stateChanged.connect(self.disable_the_threshold)
        self.add_attributes_dropdown(civic=True, tower=True)
        self.dlg.civic_layer.currentTextChanged.connect(self.civic_layer)
        self.dlg.tower_layer.currentTextChanged.connect(self.tower_layer)
        self.dlg.civic_attribute.currentTextChanged.connect(self.set_civic_attrs_value)
        self.dlg.tower_attribute.currentTextChanged.connect(self.set_tower_attrs_value)
        self.dlg.run.clicked.connect(self.startWorker)
        self.dlg.close_window.clicked.connect(self.killWorker)
        self.dlg.civic_attribute_value.checkedItemsChanged.connect(self.azimuth_dropdown)
        
        # show the dialog
        self.dlg.show()
        # Run the dialog event loop
        result = self.dlg.exec_()
        # See if OK was pressed
        if result:
            # Do something useful here - delete the line containing pass and
            # substitute with your code.
            pass
    
    def tower_layer(self):
        self.add_attributes_dropdown(tower=True)
    
    def civic_layer(self):
        self.add_attributes_dropdown(civic=True)

    def add_attributes_dropdown(self, tower=False, civic=False):
        mapcanvas = self.iface.mapCanvas()
        layersdd = mapcanvas.layers()
        tower_layer_attributes_names = list()
        civic_layer_attributes_names = list()
        tower_layer = None
        civic_layer = None
        # clear values of last layer
        if tower:
            self.dlg.tower_attribute.clear()
            self.dlg.tower_attribute_value.clear()
            tower_layer = self.dlg.tower_layer.currentText()
        if civic:
            self.dlg.civic_attribute.clear()
            self.dlg.civic_attribute_value.clear()
            civic_layer = self.dlg.civic_layer.currentText()
        # loop over all layers and add Attributes names for the drop down
        for layerdd in layersdd:
            if tower:
                if layerdd.name() == tower_layer:
                    for field in layerdd.fields():
                        if field.name() not in tower_layer_attributes_names:
                            tower_layer_attributes_names.append(field.name())
            if civic:
                if layerdd.name() == civic_layer:
                    for field in layerdd.fields():
                        if field.name() not in civic_layer_attributes_names:
                            civic_layer_attributes_names.append(field.name())
            
        # Set Attributes in GUI dropdown
        if tower:
            self.dlg.tower_attribute.addItems([None])
            self.dlg.tower_attribute.addItems(tower_layer_attributes_names)
        if civic:
            self.dlg.civic_attribute.addItems([None])
            self.dlg.civic_attribute.addItems(civic_layer_attributes_names)

    def set_tower_attrs_value(self):
        self.add_field_values(tower=True)
    
    def set_civic_attrs_value(self):
        self.add_field_values(civic=True)

    def azimuth_dropdown(self):

        self.dlg.azimuth.clear()
        selected_azi = self.dlg.civic_attribute_value.checkedItems()
        if len(selected_azi) != 0:
            unique_azimuth = list()
            for selected in selected_azi:
                splitted_ = str(selected).split('_')[-1]
                civic_azi = splitted_[1:]
                if civic_azi not in unique_azimuth:
                    unique_azimuth.append(civic_azi)
            self.dlg.azimuth.addItems(str(l) for l in unique_azimuth)
            return True        
            
        mapcanvas = self.iface.mapCanvas()
        layersdd = mapcanvas.layers()
        civic_layer = self.dlg.civic_layer.currentText()
        unique_azimuth = list()
        for layer in layersdd:
            if layer.name() == civic_layer:
                self.civic_layer_ = layer
        try:
            idx = self.civic_layer_.fields().indexOf('Best Serve')
            values = self.civic_layer_.uniqueValues(idx)
            for value in values:
                if not value:
                    continue
                splitted_ = str(value).split('_')[-1]
                civic_azi = splitted_[1:]
                if civic_azi not in unique_azimuth:
                    unique_azimuth.append(civic_azi)
        except:
            return True
        
        self.dlg.azimuth.addItems(str(l) for l in unique_azimuth)

    def disable_the_threshold(self):
        if self.dlg.threshold_check.isChecked():
            self.dlg.threshold.setEnabled(False)
        else:
            self.dlg.threshold.setEnabled(True)

    def add_field_values(self, tower=False, civic=False):
        mapcanvas = self.iface.mapCanvas()
        layersdd = mapcanvas.layers()
        attr_name = str()
        layer = str()
        list_value = None
        # clear values of last layer
        if tower:
            self.dlg.tower_attribute_value.clear()
            attr_name = self.dlg.tower_attribute.currentText()
            layer = self.dlg.tower_layer.currentText()

        if civic:
            self.dlg.civic_attribute_value.clear()
            attr_name = self.dlg.civic_attribute.currentText()
            layer = self.dlg.civic_layer.currentText()

        if list_value is None:
            for layerdd in layersdd:
                if layerdd.name() != layer:
                    continue
                for field in layerdd.fields():
                    if field.name() != attr_name:
                        continue
                    idx = layerdd.fields().indexOf(field.name())
                    values = layerdd.uniqueValues(idx)
                    list_value = list(values)
                    break
                break
        if list_value is None:
            return False
                                    
        if tower:
            self.dlg.tower_attribute_value.addItems([None])
            self.dlg.tower_attribute_value.addItems(str(l) for l in list_value)
        if civic:
            self.dlg.civic_attribute_value.addItems([None])
            self.dlg.civic_attribute_value.addItems(str(l) for l in list_value)
       
    def startWorker(self):
        self.thread = QThread()
        self.worker = Worker(self.dlg, self.iface)
        self.worker.moveToThread(self.thread) # move Worker-Class to a thread
        # Connect signals and slots:
        self.thread.started.connect(self.worker.signal_analysis)
        self.worker.progress.connect(self.reportProgress)
        self.worker.logs.connect(self.set_logs)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)

        self.thread.start() # finally start the thread
        self.dlg.run.setEnabled(False) # disable the start-thread button while thread is running
        self.thread.finished.connect(lambda: self.dlg.run.setEnabled(True)) # enable the start-thread button when thread has been finished

        # method to kill/cancel the worker thread
    def set_logs(self, logs):
        self.dlg.logs.setText(str(logs))

    def killWorker(self):         
        try: 
            self.worker.stop()
            # check if a thread is running
            if self.thread.isRunning():
                self.thread.exit() 
                self.thread.quit() 
                self.thread.wait() 
        except:
            pass
        finally:
            self.close_window()
    
    def reportProgress(self, n):

        self.dlg.progressBar.setValue(n)
        self.iface.mapCanvas().refresh()

    def close_window(self):
        self.dlg.close()