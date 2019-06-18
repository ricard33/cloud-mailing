(function () {
    "use strict";

    angular.module('cm.dashboard')
        .component('dashboard', {
            templateUrl: 'dashboard/dashboard.html',
            controller: DashboardController
        });

    function DashboardController($scope, $log, $timeout, $q, api) {
        var ctrl = this;
        var update_timer = undefined;
        ctrl.onGetMailings = onGetMailings;

        $scope.$on('$destroy', function () {
            if(update_timer !== undefined)
                $timeout.cancel(update_timer);
        });

        update_graphics();

        function update_graphics() {
            ctrl.mailings_count = api.mailings.query({'.filter': 'total'});
            ctrl.recipients_count = api.recipients.query({'.filter': 'total'});
            ctrl.satellites_count = api.satellites.query({'.filter': 'total'});

            $q.all([
                ctrl.mailings_count.$promise,
                ctrl.recipients_count.$promise,
                ctrl.satellites_count.$promise
            ]).then(function () {
                update_timer = $timeout(update_graphics, 600000);
            });
        }

        function onGetMailings(mailings) {
            ctrl.mailings = mailings;
        }

    }

}());
