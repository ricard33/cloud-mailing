
(function () {
    'use strict';

    angular.module('cm.services')
        .factory('_', LodashFactory)
    ;

    function LodashFactory($window, $log) {
        if(!$window._){
            $log.error('lodash not available!');
        }
        return $window._;

    }


})();
