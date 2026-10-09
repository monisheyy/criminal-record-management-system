import seal from '../assets/brand/crms-seal.svg';

// Full-screen branded curtain shown while useRouteTransition swaps pages.
export function RouteCurtain({ phase }) {
  return (
    <div className="route-curtain" data-phase={phase} aria-hidden="true">
      <div className="route-curtain-inner">
        <div className="route-curtain-emblem">
          <img src={seal} alt="" width="220" height="220" draggable="false" />
        </div>
        <div className="route-curtain-caption">Criminal Record Management System</div>
        <div className="route-curtain-rule" />
      </div>
    </div>
  );
}
