"use strict";

angular.module('app')

    .controller('DomainsStatsCtrl', ['$scope', '$log', '$interval', 'MessageBox', 'api', 'gettextCatalog',
        function ($scope, $log, $interval, MessageBox, api, gettextCatalog) {
            $scope.$log = $log;

        }])

;