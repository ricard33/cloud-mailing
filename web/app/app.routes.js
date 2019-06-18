(function () {
    "use strict";


    /**
     * Route configuration for the CM module.
     */
    angular
        .module('app')
        .config(configureRoutes);

    function configureRoutes($stateProvider, $urlRouterProvider) {

        //var authFunction = function(auth) { return auth.resolve() };

        // For unmatched routes
        $urlRouterProvider.otherwise('/');

        // Application routes
        $stateProvider
            .state('login', {
                url: '/login',
                templateUrl: 'login/login.html',
                controller: 'LoginController',
                controllerAs: 'login_vm'
            })
            .state('index', {
                url: '/',
                template: '<dashboard></dashboard>',
                resolve: {
                    //auth: authFunction
                }
            })
            .state('statistics', {
                url: '/statistics',
                templateUrl: 'stats/stats_index.html',
                controller: 'StatisticsCtrl',
                resolve: {
                    //auth: authFunction
                }
            })
            .state('mailings', {
                url: '/mailings',
                template: '<all-mailings></all-mailings>',
                resolve: {
                    //auth: authFunction
                }
            })
            .state('mailing-view', {
                url: '/mailings/:mailingId?p',
                templateUrl: 'mailings/ml_view.html',
                controller: 'MailingDetailsController',
                controllerAs: 'vm',
                reloadOnSearch: false,
                resolve: {
                    mailing: getMailing,
                    //auth: authFunction
                }
            })
            .state('domains-stats', {
                url: '/stats/domains',
                templateUrl: 'stats/domains.html',
                resolve: {
                    //auth: authFunction
                }
            })
            .state('tables', {
                url: '/tables',
                templateUrl: 'tables.html',
                resolve: {
                    //auth: authFunction
                }
            })
            .state('settings', {
                url: '/settings',
                template: '<settings-page></settings-page>',
                resolve: {
                    //auth: authFunction
                }
            })
            .state('settings-network', {
                url: '/settings/network',
                template: '<network-settings></network-settings>',
                resolve: {
                    //auth: authFunction
                }
            })
            .state('settings-dns', {
                url: '/settings/dns',
                template: '<todo></todo>',
                resolve: {
                    //auth: authFunction
                }
            })
            .state('settings-time', {
                url: '/settings/time',
                template: '<time-settings></time-settings>',
                resolve: {
                    //auth: authFunction
                }
            })
            .state('settings-cm', {
                url: '/settings/cm',
                templateUrl: 'settings/cm_settings.html',
                resolve: {
                    //auth: authFunction
                }
            })
            .state('settings-satellites', {
                url: '/settings/satellites',
                template: '<satellites-page></satellites-page>',
                resolve: {
                    //auth: authFunction
                }
            })
            .state('settings-auth', {
                url: '/settings/auth',
                template: '<todo></todo>',
                resolve: {
                    //auth: authFunction
                }
            })
            .state('about', {
                url: '/about',
                templateUrl: 'about/about.html'
            })
            .state('todo', {
                url: '/todo',
                template: '<todo></todo>'
            });
    }


    function getMailing(api, $stateParams){
        return api.mailings.get({id: $stateParams.mailingId}).$promise;
    }
}());
