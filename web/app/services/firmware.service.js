/**
 * Created by ricard on 25/11/2015.
 */


(function () {
    'use strict';

    angular.module('cm.fw', [])
        .factory('FirmwareService', FirmwareService)
    ;

    function FirmwareService($http, api, $rootScope, $log) {
        var service = {};

        return service;

    }


})();
