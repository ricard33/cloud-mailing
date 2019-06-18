(function () {
    "use strict";

    angular.module('app')
        .directive('datetime', function () {
            return {
                scope: {
                    value: '='
                },
                template: "{{value | date:'mediumDate'}} <span class=\"text-muted text-nowrap\"><i class=\"fa fa-clock-o\" ng-if=\"value\"></i> {{ value | date:'HH:mm' }}</span>"
            };
        });

}());