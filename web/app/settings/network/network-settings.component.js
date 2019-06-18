(function () {
    'use strict';

    angular.module('cm.settings')
        .run(configureFormly)
        .component('networkSettings', {
            templateUrl: 'settings/network/network-settings.html',
            controller: NetworkController
        });

    function configureFormly(formlyConfig) {
        // set types here
        formlyConfig.setType({
            name: "networkInterfaceTable",
            templateUrl: "app/settings/network.interface2.html"
        });
        formlyConfig.setType({
            name: 'multiselect',
            extends: 'select',
            defaultOptions: {
                ngModelAttrs: {
                    'true': {
                        value: 'multiple'
                    }
                }
            }
        });
    }


    function NetworkController($state, $log, alert, gettextCatalog, api, NgTableParams, _) {
        var originalData;
        var vm = this;
        vm.submit = submit;
        vm.cancel = cancel;
        vm.del = del;
        vm.save = save;
        vm.getEthModeLabel = getEthModeLabel;
        vm.ethModes = {};
        angular.forEach(['dhcp', 'static', 'up', 'disabled'], function(mode) {
            vm.ethModes[mode] = getEthModeLabel(mode);
        });

        var tableParams = new NgTableParams({count: 5}, {
            filterDelay: 0,
            counts: []
        });
        vm.model = {};
        vm.networkFields = getFields();
        vm.model = api.fw_network.get();


        vm.model.$promise.then(function (data) {
            originalData = angular.copy(data);
            tableParams.settings({
                dataset: data.interfaces
            });
        });

        //----------

        // function definition
        function getFields() {
            // return your fields here
            return [
                {
                    "className": "section-label",
                    "template": "<div><h2 translate>Network Bridge</h2></div>"
                },
                {
                    key: 'bridge',
                    className: "row",
                    fieldGroup: [
                        {
                            className: "row",
                            fieldGroup: [
                                {
                                    key: 'mode',
                                    className: "col-sm-4",
                                    type: 'select',
                                    templateOptions: {
                                        label: gettextCatalog.getString("Configure IPV4"),
                                        placeholder: gettextCatalog.getString('enter your first name...'),
                                        options: [
                                            {
                                                "name": gettextCatalog.getString("Using DHCP"),
                                                "value": "dhcp"
                                            },
                                            {
                                                "name": gettextCatalog.getString("Manually"),
                                                "value": "static"
                                            }
                                        ]
                                    }
                                },
                                {
                                    key: 'ip',
                                    className: "col-sm-4",
                                    type: 'input',
                                    templateOptions: {
                                        type: 'text',
                                        label: gettextCatalog.getString('IP address'),
                                        placeholder: gettextCatalog.getString('ip address...')
                                    },
                                    expressionProperties: {
                                        'templateOptions.disabled': 'model.mode !== "static"'
                                    }
                                },
                                {
                                    key: 'mask',
                                    className: "col-sm-4",
                                    type: 'input',
                                    templateOptions: {
                                        type: 'text',
                                        label: gettextCatalog.getString('Network mask'),
                                        placeholder: gettextCatalog.getString("network mask...")
                                    },
                                    expressionProperties: {
                                        'templateOptions.disabled': 'model.mode !== "static"'
                                    }
                                }
                            ]
                        }
                    ]
                },
                {
                    "className": "row",
                    "fieldGroup": [
                        {
                            key: 'default-gateway',
                            className: "col-xs-6",
                            type: 'input',
                            templateOptions: {
                                type: 'text',
                                label: gettextCatalog.getString('Gateway'),
                                placeholder: gettextCatalog.getString("enter gateway ip...")
                            },
                            expressionProperties: {
                                'templateOptions.disabled': 'model.bridge.mode === "dhcp"'
                            }
                        }
                    ]
                },
                {
                    "className": "row",
                    "fieldGroup": [
                        {
                            key: 'dns[0]',
                            className: "col-xs-6",
                            type: 'input',
                            templateOptions: {
                                type: 'text',
                                label: gettextCatalog.getString('Primary DNS'),
                                placeholder: gettextCatalog.getString("ip for primany DNS...")
                            }
                        },
                        {
                            key: 'dns[1]',
                            className: "col-xs-6",
                            type: 'input',
                            templateOptions: {
                                type: 'text',
                                label: gettextCatalog.getString('Secondary DNS'),
                                placeholder: gettextCatalog.getString("ip for secondary DNS...")
                            }
                        }
                    ]
                },
                {
                    key: 'interfaces',
                    type: 'networkInterfaceTable',
                    templateOptions: {
                        title: gettextCatalog.getString('Physical Interfaces'),
                        tableParams: tableParams,
                        cols: [
                            {field: 'name', title: gettextCatalog.getString('Name')},
                            {field: 'mode', title: gettextCatalog.getString('Configure IPV4')},
                            {field: 'ip', title: gettextCatalog.getString('IP')},
                            {field: 'mask', title: gettextCatalog.getString('Mask')},
                            {field: 'action', title: gettextCatalog.getString('Actions')}
                        ],
                        fields: [
                            {
                                key: 'name',
                                type: 'input',
                                data: {colHeader: gettextCatalog.getString('Name')},
                                templateOptions: {
                                    type: 'input'
                                },
                                expressionProperties: {'templateOptions.disabled': 'true'}
                            },
                            {
                                key: 'mode',
                                type: 'select',
                                data: {colHeader: gettextCatalog.getString('Configure IPV4')},
                                templateOptions: {
                                    options: ['dhcp', 'static', 'up', 'disabled'].map(function(mode){
                                        return {
                                            "name": getEthModeLabel(mode),
                                            "value": mode
                                        };
                                    }),
                                    ethModes: ['dhcp', 'static', 'up', 'disabled'].reduce(function(result, mode) {
                                        result[mode] = getEthModeLabel(mode);
                                        return result;
                                    }, {})
                                }
                            },
                            {
                                key: 'ip',
                                type: 'input',
                                data: {colHeader: gettextCatalog.getString('IP')},
                                templateOptions: {
                                    type: 'input',
                                    placeholder: gettextCatalog.getString('ip address...')
                                    // },
                                    // expressionProperties: {
                                    //     'templateOptions.disabled': 'model.mode !== "static"',
                                    //     'templateOptions.label': '$modelValue'
                                }
                            },
                            {
                                key: 'mask',
                                type: 'input',
                                data: {colHeader: gettextCatalog.getString('Mask')},
                                templateOptions: {
                                    type: 'input',
                                    placeholder: gettextCatalog.getString("network mask...")
                                }
                            }
                        ]
                    }, // app settings
                    data: {
                        save: save,
                        cancel: cancel,
                        del: del
                    }
                }
            ];
        }

        function submit() {
            var net_config = vm.model;
            var bridgedIntf = [];
            angular.forEach(net_config.interfaces,
                function (intf) {
                    if (intf.mode === 'up') {
                        bridgedIntf.push(intf.name);
                    }
                });
            net_config.bridge.intf_list = bridgedIntf;
            // $log.debug(net_config);
            // api.fw_network.update(net_config).$promise
            net_config.$update()
                .then(
                    function () {
                        alert.success(gettextCatalog.getString("Network configuration has been successfully updated."), null, net_config);
                    },
                    function (error) {
                        alert.error(gettextCatalog.getString("There are some errors."), undefined, error);
                    });
        }

        function cancel(row, rowForm) {
            var originalRow = resetRow(row, rowForm);
            angular.extend(row, originalRow);
        }

        function del(row) {
            _.remove(tableParams.settings().dataset, function (item) {
                return row === item;
            });
            tableParams.reload().then(function (data) {
                if (data.length === 0 && tableParams.total() > 0) {
                    tableParams.page(tableParams.page() - 1);
                    tableParams.reload();
                }
            });
        }

        function resetRow(row, rowForm) {
            row.isEditing = false;
            rowForm.$setPristine();
            vm.networkFields[0].data.tableTracker.untrack(row);
            return _.find(originalData.interfaces, function (r) {
                return r.id === row.id;
            });
        }

        function save(row, rowForm) {
            $log.debug("save");
            var originalRow = resetRow(row, rowForm);
            angular.extend(originalRow, row);
        }

        function getEthModeLabel(mode) {
            switch (mode) {
            case "dhcp":
                return gettextCatalog.getString("Using DHCP");
            case "static":
                return gettextCatalog.getString("Manually");
            case "up":
                return gettextCatalog.getString("Bridged");
            case "disabled":
                return gettextCatalog.getString("Disabled");
            default:
                return mode;
            }
        }

    }
})();
