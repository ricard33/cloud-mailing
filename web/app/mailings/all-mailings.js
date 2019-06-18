(function () {
    "use strict";

    angular.module('cm.mailings')
        .component('allMailings', {
            templateUrl: 'mailings/all-mailings.html',
            controller: AllMailingsController
        })
    ;

    function AllMailingsController($scope, $log, $timeout, MessageBox, api, gettextCatalog, mailingService, stHelper, $q) {
        var vm = this;
        vm.active_mailings = undefined;
        vm.startMailing = mailingService.startMailing;
        vm.pauseMailing = mailingService.pauseMailing;
        vm.deleteMailing = deleteMailing;
        vm.stopMailing = mailingService.stopMailing;
        vm.getActiveMailings = getActiveMailings;
        vm.getFinishedMailings = getFinishedMailings;


        function getActiveMailings(tableState) {
            return _getMailings(tableState, ['FILLING_RECIPIENTS', 'READY', 'RUNNING', 'PAUSED']).then(
                function(data) {vm.active_mailings = data;}
            );

        }
        
        function getFinishedMailings(tableState) {
            return _getMailings(tableState, ['FINISHED']).then(
                function(data) {vm.finished_mailings = data;}
            );

        }
        
        function _getMailings(tableState, status) {
            var limit = tableState.pagination.number || vm.itemByPage;
            var params = {
                status: status,
                ".filter": "default_with_total",
                ".offset": tableState.pagination.start || 0,
                ".limit": limit,
                ".sort": stHelper.addOrderingPrefix(tableState)
            };
            update(params, stHelper.getSearch(tableState));

            //$log.debug("getActiveMailings()", params);
            vm.loading = true;
            return api.mailings.query(params).$promise.then(function (data) {
                vm.loading = false;
                tableState.pagination.numberOfPages = Math.floor((data.total - 1) / limit) + 1;
                return data;
            });
        }

        function update(obj/*, …*/) {
            for (var i = 1; i < arguments.length; i++) {
                for (var prop in arguments[i]) {
                    var val = arguments[i][prop];
                    if (typeof val == "object") // this also applies to arrays or null!
                        update(obj[prop], val);
                    else
                        obj[prop] = val;
                }
            }
            return obj;
        }

        function deleteMailing(ml){
            mailingService.deleteMailing(ml).then(function(){
                var pos = vm.active_mailings.items.indexOf(ml);
                $log.debug("pos=", pos);
                if (pos < 0) {
                    pos = vm.finished_mailings.items.indexOf(ml);
                }
                if (pos >= 0) {
                    vm.active_mailings.items.splice(pos, 1);
                }
            });
        }
        
    }


}());
