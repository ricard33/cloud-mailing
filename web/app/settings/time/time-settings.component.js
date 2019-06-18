(function () {
    'use strict';

    angular.module('cm.settings')
        .component('timeSettings', {
            templateUrl: 'settings/time/time-settings.html',
            controller: TimeController
        });


    function TimeController($log, alert, gettextCatalog, api) {
        var $ctrl = this;
        $ctrl.fields = [];
        $ctrl.model = api.fw_time.get();
        $ctrl.options = {};
        $ctrl.onSubmit = onSubmit;

        getFields();


        function getFields() {
            api.fw_all_tz.query().$promise.then(
                function (result) {
                    var all_tz = result.map(function (tz) {
                        return {name: tz, value: tz};
                    });
                    // return your fields here
                    $ctrl.fields = [
                        {
                            className: "row",
                            fieldGroup: [
                                {
                                    key: 'timezone',
                                    className: "col-xs-12 col-md-6 col-lg-4",
                                    type: 'select',
                                    templateOptions: {
                                        label: gettextCatalog.getString('Local timezone'),
                                        placeholder: gettextCatalog.getString("select your timezone..."),
                                        options: all_tz
                                    }
                                }
                            ]
                        },
                        {
                            className: "row",
                            fieldGroup: [
                                {
                                    key: 'use_ntp',
                                    className: "col-xs-12",
                                    type: 'checkbox',
                                    templateOptions: {
                                        label: 'Set the date and time automatically',
                                    }
                                }
                            ]
                        },
                        {
                            className: "row",
                            fieldGroup: [
                                {
                                    key: 'current_datetime',
                                    className: "col-xs-12",
                                    type: 'datetimepicker',
                                    templateOptions: {
                                        label: gettextCatalog.getString('Current date and time'),
                                        dateOptions: {
                                            dateFormat: "dd-MMMM-yyyy"
                                        },
                                        dateFormat: "dd-MMMM-yyyy",
                                        datepickerPopup: 'dd-MMMM-yyyy',
                                        showMeridian: false
                                    },
                                    expressionProperties: {
                                        'templateOptions.hiddenTime': 'model.use_ntp',
                                        'templateOptions.hiddenDate': 'model.use_ntp'
                                    }
                                }
                            ]
                        }
                    ];
                }
            );
        }

        function onSubmit() {
            $ctrl.model.$update().then(
                function (result) {
                    $ctrl.options.updateInitialValue();
                    alert.success(gettextCatalog.getString("Settings successfully saved."),
                        gettextCatalog.getString("Date & Timezone"),
                        result);
                },
                function (result) {
                    alert.error(gettextCatalog.getString("Failled to save settings: ") + result.error,
                        gettextCatalog.getString("Date & Timezone"),
                        result);
                }
            );
        }

    }
})();
