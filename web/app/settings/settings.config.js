(function () {
    'use strict';

    angular.module('cm.settings')
        .run(configureFormly)
    ;

    function configureFormly(formlyConfig) {
        var ngModelAttrs = {};

        var attributes = [
            'ng-model',
            'min-date',
            'max-date',
            'date-disabled',
            'day-format',
            'month-format',
            'year-format',
            'year-range',
            'day-header-format',
            'day-title-format',
            'month-title-format',
            'date-format',
            'date-options',
            'hour-step',
            'minute-step',
            'show-meridian',
            'meridians',
            'readonly-time',
            'readonly-date',
            'hidden-time',
            'hidden-date',
            'mousewheel',
            'show-spinners',
            'current-text',
            'clear-text',
            'close-text'
        ];

        var bindings = [
            'ng-model',
            'min-date',
            'max-date',
            'date-disabled',
            'day-format',
            'month-format',
            'year-format',
            'year-range',
            'day-header-format',
            'day-title-format',
            'month-title-format',
            'date-format',
            'date-options',
            'hour-step',
            'minute-step',
            'show-meridian',
            'readonly-time',
            'readonly-date',
            'hidden-time',
            'hidden-date'
        ];

        angular.forEach(attributes, function (attr) {
            ngModelAttrs[camelize(attr)] = {
                attribute: attr
            };
        });

        angular.forEach(bindings, function (binding) {
            ngModelAttrs[camelize(binding)] = {
                bound: binding
            };
        });

        function camelize(string) {
            string = string.replace(/[\-_\s]+(.)?/g,

                function (match, chr) {
                    return chr ? chr.toUpperCase() : '';
                });
            // Ensure 1st char is always lowercase
            return string.replace(/^([A-Z])/, function (match, chr) {
                return chr ? chr.toLowerCase() : '';
            });
        }

        formlyConfig.setType({
            name: 'datetimepicker',
            template: '<br><datetimepicker ng-model="model[options.key]" show-spinners="true" date-format="dd MMMM yyyy" date-options="dateOptions"></datetimepicker>',
            wrapper: ['bootstrapLabel'],
            defaultOptions: {
                ngModelAttrs: ngModelAttrs,
                templateOptions: {
                    label: 'Time',
                    minDate: '04/01/2016'
                }
            }
        });
    }

}());
