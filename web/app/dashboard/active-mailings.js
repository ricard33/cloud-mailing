(function () {
    "use strict";

    angular.module('cm.dashboard')
        .component('activeMailings', {
            templateUrl: 'dashboard/active-mailings.html',
            controller: ActiveMailingsController,
            bindings: {
                onGetMailings: '&'
            }
        });

    function ActiveMailingsController($scope, $log, $timeout, $q, api) {
        var ctrl = this;
        var update_timer = undefined;

        $scope.$on('$destroy', function () {
            if (update_timer !== undefined)
                $timeout.cancel(update_timer);
        });

        update_graphics();

        function update_graphics() {
            api.mailings.query({
                status: ['RUNNING'],
                '.filter': 'default_with_total',
                '.sort': '-start_time'
            }).$promise.then(function(data){
                ctrl.mailings = data;
                ctrl.onGetMailings({mailings: data});
            }).then(function () {
                update_timer = $timeout(update_graphics, 60000);
            });
        }

    }

}());
