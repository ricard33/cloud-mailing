(function () {
    "use strict";

    angular.module('app')
        .directive('pageSelect', function () {
            return {
                restrict: 'E',
                template: '<input type="text" class="select-page" ng-model="inputPage" ng-change="selectPage(inputPage)">',
                link: function (scope, element, attrs) {  // eslint-disable-line no-unused-vars
                    scope.$watch('currentPage', function (c) {
                        scope.inputPage = c;
                    });
                }
            };
        });

}());