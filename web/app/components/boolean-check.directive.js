(function () {
    "use strict";

    angular.module('app')
        .directive('booleanCheck', function () {
            return {
                scope: {
                    value: '@'
                },
                template: '<i class="glyphicon glyphicon-ok text-success" ng-if="value==\'true\'"></i><i class="glyphicon glyphicon-remove text-danger" ng-if="value!=\'true\'"></i>'
            };
        });

}());