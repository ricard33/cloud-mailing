/**
 * Main app layout
 */

(function () {
    'use strict';
    angular.module('app')
        .component('layout', {
            templateUrl: 'layout/layout.html',
            controller: layoutController
        });

    function layoutController($scope, $cookies, $log, api, auth, $state, AUTH_EVENTS) {
        /**
         * Sidebar Toggle & Cookie Control
         */
        var vm = this;
        vm.user = auth.getCurrentUser();
        vm.cm = api.cm.get();
        vm.logout = logout;
        vm.toggleSidebar = toggleSidebar;

        var mobileView = 992;

        angular.forEach([AUTH_EVENTS.loginSuccess, AUTH_EVENTS.logoutSuccess, AUTH_EVENTS.sessionTimeout], function(eventType) {
            $scope.$on(eventType, function (/*event*/) {
                // $log.debug("Event received:", event);
                vm.user = auth.getCurrentUser();
            });
        });

        $scope.$watch(getWidth, function (newValue, oldValue) {   // eslint-disable-line no-unused-vars
            if (newValue >= mobileView) {
                if (angular.isDefined($cookies.get('toggle'))) {
                    vm.toggle = !$cookies.get('toggle') ? false : true;
                } else {
                    vm.toggle = true;
                }
            } else {
                vm.toggle = false;
            }

        });

        window.onresize = function () {
            $scope.$apply();
        };

        function logout(){
            $log.info("Logout...");
            auth.logout().then(function(result){
                auth.clearCredentials();
                return $state.go('login');
            })
        }

        function getWidth() {
            return window.innerWidth;
        }

        function toggleSidebar() {
            vm.toggle = !vm.toggle;
            $cookies.put('toggle', vm.toggle);
        }
    }
}());
