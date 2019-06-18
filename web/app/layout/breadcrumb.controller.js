(function () {
    'use strict';

    angular.module('app')
        .controller('BreadcrumbController', BreadcrumbController);

    function BreadcrumbController($scope, $rootScope, breadcrumbs, $log) {
        $scope.breadcrumbs = breadcrumbs;
        $scope.show_hide_menu = function () {
            $rootScope.$broadcast('cm.show_hide_menu');
        }
    }
}());
