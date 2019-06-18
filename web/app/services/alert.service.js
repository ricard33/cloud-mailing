(function () {
    'use strict';

    angular.module('cm.alert', [])
        .constant('toastr', toastr)     // eslint-disable-line no-undef
        .factory('alert', AlertService);


    function AlertService($log, toastr) {
        return {
            showToasts: true,

            error: error,
            info: info,
            success: success,
            warning: warning,

            log: $log.log
        };

        function error(message, title, data) {
            toastr.error(message, title);
            $log.error('Error: ' + message, data);
        }

        function info(message, title, data) {
            toastr.info(message, title);
            $log.info('Info: ' + message, data);
        }

        function success(message, title, data) {
            toastr.success(message, title);
            $log.info('Success: ' + message, data);
        }

        function warning(message, title, data) {
            toastr.warning(message, title);
            $log.warn('Warning: ' + message, data);
        }
    }

}());
