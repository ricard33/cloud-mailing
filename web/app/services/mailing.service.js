(function () {
    'use strict';

    angular
        .module('cm.mailing-service', ['cm.services'])
        .factory('mailingService', mailingService)
    ;

    function mailingService(api, MessageBox, gettextCatalog, $log) {
        var service = {
            startMailing: start_mailing,
            pauseMailing: pause_mailing,
            deleteMailing: delete_mailing,
            stopMailing: stop_mailing
        };
        return service;


        function start_mailing(ml) {
            return MessageBox.open(
                gettextCatalog.getString("Confirmation"),
                gettextCatalog.getString("Do you really want to start this mailing ?")
            ).result.then(function () {
                var new_status = 'READY';
                if (ml.status === 'PAUSED' && ml.start_date !== undefined)
                    new_status = 'RUNNING';
                return api.mailings.patch({id: ml.id}, {status: new_status}).$promise
                    .then(function (data) {
                        ml.status = data.status;
                    });
            }, function () {
                //$log.info('Modal dismissed at: ' + new Date());
            });
        }

        function pause_mailing(ml) {
            //$log.debug(ml.id, ml);
            return MessageBox.open(
                gettextCatalog.getString("Confirmation"),
                gettextCatalog.getString("Do you really want to pause this mailing ?")
            ).result.then(function () {
                return api.mailings.patch({id: ml.id}, {status: 'PAUSED'}).$promise
                    .then(function (data) {
                        ml.status = data.status;
                    });
            }, function () {
                //$log.info('Modal dismissed at: ' + new Date());
            });
        }

        function stop_mailing(ml) {
            //$log.debug(ml.id, ml);
            return MessageBox.open(
                gettextCatalog.getString("Confirmation"),
                gettextCatalog.getString("Do you really want to terminate this mailing ?")
            ).result.then(function () {
                return api.mailings.patch({id: ml.id}, {status: 'FINISHED'}).$promise
                    .then(function (data) {
                        ml.status = data.status;
                    });
            }, function () {
                //$log.info('Modal dismissed at: ' + new Date());
            });
        }

        function delete_mailing(ml) {
            return MessageBox.open(
                gettextCatalog.getString("Confirmation"),
                gettextCatalog.getString("Do you really want to delete this mailing ? All its data will be lost!")
            ).result.then(function () {
                return api.mailings.delete({id: ml.id}).$promise;
            }, function () {
                //$log.info('Modal dismissed at: ' + new Date());
            });
        }

    }

}());
